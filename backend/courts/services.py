import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Court, QueueEntry

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


def create_queue_entry(court, usernames, created_by):
    if len(usernames) not in settings.ALLOWED_GROUP_SIZES:
        raise ServiceError(
            f"Group size must be one of {settings.ALLOWED_GROUP_SIZES}, got {len(usernames)}."
        )
    if len(set(usernames)) != len(usernames):
        raise ServiceError("Duplicate usernames in the same group are not allowed.")
    if created_by.username not in usernames:
        raise ServiceError("The signing-in user must be included in their own group.")

    users = list(User.objects.filter(username__in=usernames))
    found_usernames = {u.username for u in users}
    missing = set(usernames) - found_usernames
    if missing:
        raise ServiceError(f"Unknown username(s): {', '.join(sorted(missing))}.")

    reap_expired_reservations(court_ids=[court.id])

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)

        conflicting = (
            QueueEntry.objects.filter(
                court=locked_court,
                status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
                members__in=users,
            )
            .values_list("members__username", flat=True)
            .distinct()
        )
        conflicting_names = sorted(set(conflicting) & found_usernames)
        if conflicting_names:
            raise ServiceError(
                f"Already signed up on {locked_court.name}: {', '.join(conflicting_names)}."
            )

        entry = QueueEntry.objects.create(
            court=locked_court, created_by=created_by, status=QueueEntry.Status.WAITING
        )
        entry.members.set(users)

        _promote_next_if_free(locked_court)

    entry.refresh_from_db()
    return entry


def unsign(entry, usernames, requesting_user):
    current_members = list(entry.members.all())
    current_usernames = {u.username for u in current_members}

    if requesting_user.username not in current_usernames:
        raise ServiceError("You are not a member of this group.")
    if entry.status not in (QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE):
        raise ServiceError("This entry is no longer active or waiting.")
    if len(usernames) == 0 or len(usernames) % 2 != 0:
        raise ServiceError("Must unsign an even number of players (at least 2 at a time).")
    if not set(usernames).issubset(current_usernames):
        raise ServiceError("Can only unsign players who are currently in this group.")

    remaining_count = len(current_usernames) - len(usernames)
    if remaining_count not in (0, *settings.ALLOWED_GROUP_SIZES):
        raise ServiceError(
            f"Removing {len(usernames)} would leave {remaining_count} players, which isn't allowed."
        )

    court = entry.court
    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)
        entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)
        entry.members.remove(*[u for u in current_members if u.username in usernames])

        if remaining_count == 0:
            was_active = entry.status == QueueEntry.Status.ACTIVE
            entry.status = (
                QueueEntry.Status.COMPLETED if was_active else QueueEntry.Status.CANCELLED
            )
            entry.ended_at = timezone.now()
            entry.save()
            if was_active:
                _promote_next_if_free(locked_court)

    entry.refresh_from_db()
    return entry
