import datetime

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import activity_log
from .models import Court, CourtActivityLog, Pair, PlayerSession, QueueEntry

User = get_user_model()


class ServiceError(Exception):
    """Raised for business-rule violations; views translate this to a JSON
    error response using `status` (default 400)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


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
    for pair in next_entry.pairs.select_related("player_1", "player_2").all():
        activity_log.log_pair_event(
            CourtActivityLog.EventType.PAIR_ACTIVATED, court, next_entry, pair
        )


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
                for pair in active.pairs.select_related("player_1", "player_2").all():
                    activity_log.log_pair_event(
                        CourtActivityLog.EventType.PAIR_ENDED,
                        locked_court,
                        active,
                        pair,
                        reason=CourtActivityLog.Reason.EXPIRED,
                    )
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
    if not court.is_active or not court.location.is_active:
        raise ServiceError(f"{court.name} is not currently available.")
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
        created_pairs = []
        for slot, group in enumerate(pairs, start=1):
            pair = Pair.objects.create(
                entry=entry,
                slot=slot,
                player_1=users_by_username[group[0]],
                player_2=users_by_username[group[1]],
                created_by=created_by,
            )
            created_pairs.append(pair)

        _promote_next_if_free(locked_court)

        entry.refresh_from_db()
        if entry.status == QueueEntry.Status.WAITING:
            for pair in created_pairs:
                activity_log.log_pair_event(
                    CourtActivityLog.EventType.PAIR_QUEUED, locked_court, entry, pair
                )

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
    if not entry.court.is_active or not entry.court.location.is_active:
        raise ServiceError(f"{entry.court.name} is not currently available.")
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

        pair = Pair.objects.create(
            entry=locked_entry,
            slot=open_slot,
            player_1=users_by_username[usernames[0]],
            player_2=users_by_username[usernames[1]],
            created_by=requesting_user,
        )
        activity_log.log_pair_event(
            CourtActivityLog.EventType.OPEN_SLOT_JOINED, locked_court, locked_entry, pair
        )

    entry.refresh_from_db()
    return entry


def _end_pair(locked_court, locked_entry, pair, reason, actor=None):
    """Delete one pair from an entry whose Court+QueueEntry the caller
    already holds select_for_update() locks on, logging why before it's
    gone. If it was the entry's last pair, close out the entry
    (completed/cancelled) and promote the next waiting entry if it was
    active. Shared by the player-initiated `unsign_pair` and the
    admin-initiated removal actions."""
    activity_log.log_pair_event(
        CourtActivityLog.EventType.PAIR_ENDED, locked_court, locked_entry, pair,
        reason=reason, actor=actor,
    )
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

        _end_pair(locked_court, locked_entry, pair, reason=CourtActivityLog.Reason.UNSIGNED)

    entry.refresh_from_db()
    return entry


def verify_pair_credentials(pairs_credentials, requesting_user):
    """`pairs_credentials` is a list of 1-2 groups, each a list of 2
    {"username", "password"} dicts. Every member's password is verified via
    Django's authenticate() except the requesting (already session-
    authenticated) user's own. Returns the equivalent plain
    [[username, username], ...] structure for services.create_queue_entry /
    join_open_slot, which are otherwise unchanged."""
    result = []
    for group in pairs_credentials:
        usernames = []
        for member in group:
            username = member.get("username", "")
            if username != requesting_user.username:
                password = member.get("password", "")
                verified = authenticate(username=username, password=password)
                if verified is None:
                    raise ServiceError(f"Incorrect username or password for {username}.")
            usernames.append(username)
        result.append(usernames)
    return result


def create_player_session(user, location):
    """Authenticates `user` for `location`. Regular players are limited to
    one active session system-wide: if they currently hold an active/
    waiting pair at a *different* location, the switch is rejected (409)
    rather than silently ending their game there. Admins are exempt from
    both the conflict check and the single-session limit."""
    if not user.is_staff:
        conflict = (
            Pair.objects.filter(
                Q(player_1=user) | Q(player_2=user),
                entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
            )
            .exclude(entry__court__location=location)
            .select_related("entry__court__location")
            .first()
        )
        if conflict:
            loc = conflict.entry.court.location
            court = conflict.entry.court
            raise ServiceError(
                f"Still signed in at {loc.name} (Court {court.number}). "
                f"Leave that court before switching facilities.",
                status=409,
            )
        PlayerSession.objects.filter(user=user).delete()

    session = PlayerSession.objects.create(user=user, location=location)
    activity_log.log_login(user, location)
    return session
