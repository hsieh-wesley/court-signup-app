import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Court, Pair, QueueEntry

User = get_user_model()


class ServiceError(Exception):
    """Raised for business-rule violations; views translate this to a 400."""


def _reservation_expiry(now):
    return now + datetime.timedelta(minutes=settings.RESERVATION_DURATION_MINUTES)


def _promote_next_if_free(court):
    """Activate the oldest waiting entry if the court has no active entry."""
    if QueueEntry.objects.filter(court=court, status=QueueEntry.Status.ACTIVE).exists():
        return
    next_entry = (
        QueueEntry.objects.select_for_update()
        .filter(court=court, status=QueueEntry.Status.WAITING)
        .order_by("created_at", "id")
        .first()
    )
    if next_entry is None:
        return
    now = timezone.now()
    next_entry.status = QueueEntry.Status.ACTIVE
    next_entry.activated_at = now
    next_entry.expires_at = _reservation_expiry(now)
    next_entry.save()


def reap_expired_reservations(court_ids=None):
    """Close out any active reservation whose time is up and promote the next
    waiting entry. Called lazily on every board read and before/after
    join/unsign, rather than via a background worker (see plan TODO)."""
    courts = Court.objects.all()
    if court_ids is not None:
        courts = courts.filter(id__in=court_ids)

    for court in courts:
        with transaction.atomic():
            locked_court = Court.objects.select_for_update().get(pk=court.pk)
            active = (
                QueueEntry.objects.select_for_update()
                .filter(court=locked_court, status=QueueEntry.Status.ACTIVE)
                .first()
            )
            if active and active.expires_at and active.expires_at <= timezone.now():
                active.status = QueueEntry.Status.EXPIRED
                active.ended_at = timezone.now()
                active.save()
            _promote_next_if_free(locked_court)


def _conflicting_usernames(locked_court, usernames):
    """Usernames among `usernames` already waiting/active on this court."""
    existing_pairs = Pair.objects.filter(
        entry__court=locked_court,
        entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
    ).select_related("player_1", "player_2")
    existing_usernames = set()
    for pair in existing_pairs:
        existing_usernames.add(pair.player_1.username)
        existing_usernames.add(pair.player_2.username)
    return sorted(existing_usernames & set(usernames))


def create_queue_entry(court, pairs, created_by):
    """`pairs` is a list of 1 or 2 [username, username] groups."""
    if len(pairs) not in (1, 2):
        raise ServiceError("Must submit 1 or 2 pairs.")
    for group in pairs:
        if len(group) != 2:
            raise ServiceError("Each pair must have exactly 2 players.")

    flat = [username for group in pairs for username in group]
    if len(flat) not in settings.ALLOWED_GROUP_SIZES:
        raise ServiceError(
            f"Group size must be one of {settings.ALLOWED_GROUP_SIZES}, got {len(flat)}."
        )
    if len(set(flat)) != len(flat):
        raise ServiceError("Duplicate usernames in the same group are not allowed.")
    if created_by.username not in flat:
        raise ServiceError("The signing-in user must be included in their own group.")

    users_by_username = {u.username: u for u in User.objects.filter(username__in=flat)}
    missing = set(flat) - users_by_username.keys()
    if missing:
        raise ServiceError(f"Unknown username(s): {', '.join(sorted(missing))}.")

    reap_expired_reservations(court_ids=[court.id])

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)

        conflicting_names = _conflicting_usernames(locked_court, flat)
        if conflicting_names:
            raise ServiceError(
                f"Already signed up on {locked_court.name}: {', '.join(conflicting_names)}."
            )

        entry = QueueEntry.objects.create(
            court=locked_court, created_by=created_by, status=QueueEntry.Status.WAITING
        )
        for slot, group in enumerate(pairs, start=1):
            Pair.objects.create(
                entry=entry,
                slot=slot,
                player_1=users_by_username[group[0]],
                player_2=users_by_username[group[1]],
                created_by=created_by,
            )

        _promote_next_if_free(locked_court)

    entry.refresh_from_db()
    return entry


def join_open_slot(entry, usernames, requesting_user):
    """Fill a WAITING entry's one remaining open slot with a new pair.

    Locks Court then QueueEntry, same order as every other write path here,
    so a join can never race a promotion of the same entry: whichever
    transaction commits first is authoritative, and the other re-reads
    entry.status/pairs under its own lock and fails cleanly instead of
    double-filling a slot.
    """
    if len(usernames) != 2:
        raise ServiceError("A joining group must be exactly one pair (2 players).")
    if len(set(usernames)) != 2:
        raise ServiceError("Duplicate usernames in the same group are not allowed.")
    if requesting_user.username not in usernames:
        raise ServiceError("The signing-in user must be included in their own pair.")

    users_by_username = {u.username: u for u in User.objects.filter(username__in=usernames)}
    missing = set(usernames) - users_by_username.keys()
    if missing:
        raise ServiceError(f"Unknown username(s): {', '.join(sorted(missing))}.")

    court = entry.court
    reap_expired_reservations(court_ids=[court.id])

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)
        locked_entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)

        if locked_entry.status != QueueEntry.Status.WAITING:
            raise ServiceError("This position is no longer open to join.")

        occupied_slots = set(locked_entry.pairs.values_list("slot", flat=True))
        if len(occupied_slots) >= 2:
            raise ServiceError("This position is already full.")
        open_slot = 1 if 1 not in occupied_slots else 2

        conflicting_names = _conflicting_usernames(locked_court, usernames)
        if conflicting_names:
            raise ServiceError(
                f"Already signed up on {locked_court.name}: {', '.join(conflicting_names)}."
            )

        Pair.objects.create(
            entry=locked_entry,
            slot=open_slot,
            player_1=users_by_username[usernames[0]],
            player_2=users_by_username[usernames[1]],
            created_by=requesting_user,
        )

    entry.refresh_from_db()
    return entry


def unsign_pair(entry, pair_id, requesting_user):
    """Remove one whole pair from an entry. Any current member of the entry
    may unsign any pair, not just their own — matches the trust model of
    the original flat-membership unsign."""
    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=entry.court_id)
        locked_entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)

        current_usernames = set()
        for pair in locked_entry.pairs.all():
            current_usernames.add(pair.player_1.username)
            current_usernames.add(pair.player_2.username)
        if requesting_user.username not in current_usernames:
            raise ServiceError("You are not a member of this group.")
        if locked_entry.status not in (QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE):
            raise ServiceError("This entry is no longer active or waiting.")

        try:
            pair = locked_entry.pairs.get(pk=pair_id)
        except Pair.DoesNotExist:
            raise ServiceError("That pair is not part of this entry.")

        pair.delete()
        remaining = locked_entry.pairs.count()

        if remaining == 0:
            was_active = locked_entry.status == QueueEntry.Status.ACTIVE
            locked_entry.status = (
                QueueEntry.Status.COMPLETED if was_active else QueueEntry.Status.CANCELLED
            )
            locked_entry.ended_at = timezone.now()
            locked_entry.save()
            if was_active:
                _promote_next_if_free(locked_court)

    entry.refresh_from_db()
    return entry
