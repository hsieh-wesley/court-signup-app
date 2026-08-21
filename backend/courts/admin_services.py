import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from . import activity_log
from .membership import active_membership, find_active_membership_by_phone
from .models import (
    Court,
    CourtActivityLog,
    Location,
    LoginLog,
    Membership,
    Pair,
    Player,
    PlayerSession,
    QueueEntry,
)
from .password_gen import generate_admin_password, generate_password, generate_unique_passwords
from .services import ServiceError, _end_pair, validate_new_username

User = get_user_model()

PHONE_RE = re.compile(r"^\d{10}$")


def _validate_phone(phone_number):
    if not PHONE_RE.match(phone_number or ""):
        raise ServiceError("Phone number must be exactly 10 digits.")


def create_player(display_name, username=None, enable_login=False):
    """Returns (player, plaintext_password_or_None)."""
    if not display_name:
        raise ServiceError("display_name is required.")
    if enable_login and not username:
        raise ServiceError("username is required when enable_login is true.")
    if username:
        validate_new_username(username)

    with transaction.atomic():
        plaintext = None
        user = None
        if enable_login:
            plaintext = generate_password()
            user = User.objects.create_user(username=username, password=plaintext)
        player = Player.objects.create(
            display_name=display_name, user=user, current_password_plaintext=plaintext or ""
        )

    return player, plaintext


def edit_player(player, display_name=None, username=None):
    if display_name is not None:
        player.display_name = display_name
    if username is not None:
        if player.user is None:
            raise ServiceError("This player has no login access to rename.")
        validate_new_username(username, exclude_user_id=player.user_id)
        player.user.username = username
        player.user.save()
    player.save()
    return player


def add_login(player, username):
    """Grants (or re-grants) login access, generating a fresh password
    either way. Reuses the existing auth.User row if this player previously
    had login and it was disabled, rather than creating a duplicate."""
    if player.user is not None:
        user = player.user
        if username != user.username:
            validate_new_username(username, exclude_user_id=user.pk)
        user.username = username
        user.is_active = True
        plaintext = generate_password()
        user.set_password(plaintext)
        user.save()
        PlayerSession.objects.filter(user=user).delete()
        player.current_password_plaintext = plaintext
        player.save(update_fields=["current_password_plaintext"])
        return plaintext

    validate_new_username(username)
    plaintext = generate_password()
    user = User.objects.create_user(username=username, password=plaintext)
    player.user = user
    player.current_password_plaintext = plaintext
    player.save()
    return plaintext


def disable_login(player):
    if player.user is None:
        raise ServiceError("This player has no login access.")
    player.user.is_active = False
    player.user.save()
    PlayerSession.objects.filter(user=player.user).delete()


def reset_password(player):
    if player.user is None:
        raise ServiceError("This player has no login access.")
    plaintext = generate_password()
    player.user.set_password(plaintext)
    player.user.save()
    PlayerSession.objects.filter(user=player.user).delete()
    player.current_password_plaintext = plaintext
    player.save(update_fields=["current_password_plaintext"])
    return plaintext


def _remove_all_pairs_for_user(user, actor=None):
    """Ends every active/waiting pair this user currently belongs to, on
    any court, promoting the next queued entry on each affected court."""
    pairs = Pair.objects.filter(
        Q(player_1=user) | Q(player_2=user),
        entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
    ).select_related("entry")
    for pair in pairs:
        with transaction.atomic():
            locked_court = Court.objects.select_for_update().get(pk=pair.entry.court_id)
            locked_entry = QueueEntry.objects.select_for_update().get(pk=pair.entry_id)
            try:
                locked_pair = locked_entry.pairs.get(pk=pair.pk)
            except Pair.DoesNotExist:
                continue
            _end_pair(
                locked_court, locked_entry, locked_pair,
                reason=CourtActivityLog.Reason.PLAYER_DEACTIVATED, actor=actor,
            )


def deactivate_player(player, actor=None):
    """Archives the player and, if they have login, disables it too and
    clears any current court/queue assignment. The Player row itself is
    never deleted (Pair/QueueEntry rows have PROTECT FKs to auth.User, so
    hard-deleting anyone with play history isn't possible without a bigger
    migration — archiving is the supported path)."""
    if player.user is not None:
        _remove_all_pairs_for_user(player.user, actor=actor)
        disable_login(player)
    player.is_active = False
    player.save()


def player_can_delete(player):
    """A non-member with no real court/queue activity — the only case a
    permanent delete is offered for. Members are never deletable this
    way (their identity stays attached to their membership history);
    neither is anyone who ever actually played (Pair/QueueEntry rows
    PROTECT their player FKs regardless)."""
    if Membership.objects.filter(player=player).exists():
        return False
    if player.user is None:
        return True
    user = player.user
    return not (
        QueueEntry.objects.filter(created_by=user).exists()
        or Pair.objects.filter(Q(player_1=user) | Q(player_2=user) | Q(created_by=user)).exists()
    )


def delete_player(player):
    """Permanently deletes a non-member player with no court/queue
    activity. By explicit product decision, a non-member's identity
    isn't preserved long-term — only aggregate history matters for them
    (CourtActivityLog rows snapshot usernames as plain text, not a FK, so
    those stay intact and readable either way) — so their LoginLog rows
    (registration/check-in events) are deleted along with the account,
    unlike every other delete in this app which refuses to touch
    history. Members and anyone with real play history are refused; see
    player_can_delete."""
    if not player_can_delete(player):
        raise ServiceError(
            f"{player.display_name} has membership or play history and can't be permanently "
            "deleted. Deactivate instead.",
            status=409,
        )
    with transaction.atomic():
        user = player.user
        player.delete()
        if user is not None:
            LoginLog.objects.filter(user=user).delete()
            user.delete()


def start_membership(username, phone_number, starts_at=None, expires_at=None, location=None):
    """Starts a new Membership period for `username` — reusing their
    existing Player/User if one already exists (e.g. a non-member who
    self-registered months ago and is now becoming a member) rather than
    ever creating a duplicate account to represent the same person.
    `location=None` means "All Locations" (valid everywhere) — the same
    phone number is never allowed to be active for two different members
    regardless of location scope, since it's a real-world identifier, not
    a per-facility one. Returns (player, plaintext_or_None) — plaintext
    only when a brand-new account was created here; an existing account
    keeps its existing password (their first check-in draws a fresh
    member-only one)."""
    _validate_phone(phone_number)

    phone_conflict = find_active_membership_by_phone(phone_number)

    try:
        user = User.objects.get(username__iexact=username)
        player = user.player
        plaintext = None
    except User.DoesNotExist:
        validate_new_username(username)
        plaintext = generate_password()
        user = User.objects.create_user(username=username, password=plaintext)
        player = Player.objects.create(
            display_name=username, user=user, current_password_plaintext=plaintext
        )

    if phone_conflict is not None and phone_conflict.player_id != player.id:
        raise ServiceError("That phone number is already active for another member.")
    if active_membership(player) is not None:
        raise ServiceError(f"{username} already has an active membership.")

    with transaction.atomic():
        membership = Membership.objects.create(
            player=player,
            phone_number=phone_number,
            location=location,
            starts_at=starts_at or timezone.now(),
            expires_at=expires_at,
        )

    return player, membership, plaintext


_UNSET = object()


def update_membership(membership, phone_number=None, expires_at=None, location=_UNSET):
    """In-place edits to a CURRENT (not-yet-lapsed) Membership row. Phone
    number is just contact info; only the start/expire *boundaries* matter
    for history, and those stay protected by never mutating an already-
    lapsed row — renewal always goes through start_membership instead.
    `location` uses a sentinel default (not None) so a partial edit that
    doesn't mention it leaves the existing scope untouched — None is a
    real, meaningful value here ("All Locations"), not "unspecified"."""
    now = timezone.now()
    if membership.expires_at and membership.expires_at <= now:
        raise ServiceError("This membership period has ended — start a new one instead of editing it.")

    if phone_number is not None:
        _validate_phone(phone_number)
        conflict = find_active_membership_by_phone(phone_number)
        if conflict is not None and conflict.player_id != membership.player_id:
            raise ServiceError("That phone number is already active for another member.")
        membership.phone_number = phone_number
    if expires_at is not None:
        membership.expires_at = expires_at
    if location is not _UNSET:
        membership.location = location
    membership.save()
    return membership


def reset_staff_password():
    """Admin-only (enforced at the view layer). In place, no account
    recreation — a fresh secure password replaces the old one via the
    normal Django hashing (set_password), and any existing staff
    PlayerSession is invalidated immediately. The plaintext is returned
    once for display and never stored or retrievable again afterward."""
    try:
        staff = User.objects.get(username="staff")
    except User.DoesNotExist:
        raise ServiceError("No staff account exists yet — run seed_staff_account first.")
    plaintext = generate_admin_password()
    staff.set_password(plaintext)
    staff.save()
    PlayerSession.objects.filter(user=staff).delete()
    return plaintext


def create_test_players(n=8):
    """Idempotent: re-running this reuses player1..playerN if they already
    exist and just regenerates their passwords, so it's safe to use as a
    'reset my test accounts' button during development."""
    passwords = generate_unique_passwords(n)
    results = []
    for i in range(1, n + 1):
        username = f"player{i}"
        display_name = f"Player {i}"
        plaintext = passwords[i - 1]
        try:
            user = User.objects.get(username=username)
            user.set_password(plaintext)
            user.is_active = True
            user.save()
            PlayerSession.objects.filter(user=user).delete()
            player = getattr(user, "player", None)
            if player is None:
                player = Player.objects.create(
                    user=user, display_name=display_name, current_password_plaintext=plaintext
                )
            else:
                player.is_active = True
                player.display_name = display_name
                player.current_password_plaintext = plaintext
                player.save()
        except User.DoesNotExist:
            user = User.objects.create_user(username=username, password=plaintext)
            Player.objects.create(
                user=user, display_name=display_name, current_password_plaintext=plaintext
            )
        results.append(
            {"username": username, "password": plaintext, "display_name": display_name}
        )
    return results


def create_location(name, court_count=10):
    if not name:
        raise ServiceError("name is required.")
    if Location.objects.filter(name=name).exists():
        raise ServiceError(f"A location named '{name}' already exists.")
    if not (1 <= court_count <= 100):
        raise ServiceError("Court count must be between 1 and 100.")
    with transaction.atomic():
        location = Location.objects.create(name=name)
        for n in range(1, court_count + 1):
            Court.objects.create(location=location, number=n)
    return location


def deactivate_location(location, actor=None):
    """Drops any occupied courts first, then deactivates the location.
    Individual courts keep their own is_active value — only new signups
    (via the location-active check in services.py) are blocked."""
    for court in location.courts.filter(is_active=True):
        if QueueEntry.objects.filter(
            court=court, status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE]
        ).exists():
            drop_court(court, actor=actor)
    location.is_active = False
    location.save()


def edit_location(location, name=None, is_active=None):
    if name is not None:
        if Location.objects.exclude(pk=location.pk).filter(name=name).exists():
            raise ServiceError(f"A location named '{name}' already exists.")
        location.name = name
        location.save()
    if is_active is False and location.is_active:
        deactivate_location(location)
    elif is_active is True and not location.is_active:
        location.is_active = True
        location.save()
    return location


def location_has_history(location):
    """True if anything about this location was ever recorded — a
    check-in, a court event, or a queue entry on any of its courts (past
    or present, regardless of that entry's own status). Court/LoginLog/
    CourtActivityLog all PROTECT their location FK, so this mirrors
    exactly what the database would refuse to cascade-delete through."""
    return (
        LoginLog.objects.filter(location=location).exists()
        or CourtActivityLog.objects.filter(location=location).exists()
        or QueueEntry.objects.filter(court__location=location).exists()
    )


def delete_location(location):
    """Permanently deletes a location only when it has zero historical
    footprint. Otherwise refuses — deactivating (see deactivate_location)
    is the supported way to retire a location that has any history, since
    hard-deleting it would either violate the PROTECT constraints on
    Court/LoginLog/CourtActivityLog or, worse, silently take real history
    down with it."""
    if location_has_history(location):
        raise ServiceError(
            f"{location.name} has recorded history (check-ins, court activity, or "
            "past queue entries) and can't be permanently deleted. Deactivate it "
            "instead — it disappears from kiosk selection but its history stays intact.",
            status=409,
        )
    with transaction.atomic():
        location.courts.all().delete()
        location.delete()


def set_court_count(location, target_count, actor=None):
    """Increasing reuses existing (deactivated) Court rows for numbers that
    already exist rather than creating duplicates — required by the
    unique(location, number) constraint anyway, and preserves court
    identity/history. Decreasing deactivates (never deletes) courts above
    the new target, safely dropping any current occupants first."""
    if not (1 <= target_count <= 100):
        raise ServiceError("Court count must be between 1 and 100.")

    existing = {c.number: c for c in location.courts.all()}

    for n in range(1, target_count + 1):
        if n in existing:
            court = existing[n]
            if not court.is_active:
                court.is_active = True
                court.save()
                activity_log.log_court_event(
                    CourtActivityLog.EventType.COURT_REACTIVATED, court, actor=actor
                )
        else:
            Court.objects.create(location=location, number=n)

    for n in sorted(existing):
        if n > target_count and existing[n].is_active:
            deactivate_court(existing[n], actor=actor)

    return location


def create_court(location, number=None, capacity=None):
    if number is None:
        max_number = location.courts.aggregate(m=Max("number"))["m"] or 0
        number = max_number + 1
    if not (1 <= number <= 100):
        raise ServiceError("Court number must be between 1 and 100.")
    if location.courts.filter(number=number).exists():
        raise ServiceError(f"Court {number} already exists at {location.name}.")
    kwargs = {"location": location, "number": number}
    if capacity is not None:
        kwargs["capacity"] = capacity
    return Court.objects.create(**kwargs)


def remove_player_from_court(court, username, actor=None):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        raise ServiceError(f"Unknown username: {username}.")

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)
        pair = (
            Pair.objects.select_for_update()
            .filter(
                Q(player_1=user) | Q(player_2=user),
                entry__court=locked_court,
                entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
            )
            .select_related("entry")
            .first()
        )
        if pair is None:
            raise ServiceError(f"{username} is not currently on {locked_court.name}.")
        locked_entry = QueueEntry.objects.select_for_update().get(pk=pair.entry_id)
        _end_pair(
            locked_court, locked_entry, pair,
            reason=CourtActivityLog.Reason.ADMIN_REMOVED, actor=actor,
        )


def drop_court(court, actor=None):
    """Ends every active/waiting entry on this court in one shot, logging
    one PAIR_ENDED per pair plus exactly one COURT_DROPPED for the action
    itself (so an empty court's drop still shows up in history). No
    promotion afterward — every entry on the court is being cleared, so
    there's nothing left to promote. The court row is untouched."""
    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)
        entries = QueueEntry.objects.select_for_update().filter(
            court=locked_court,
            status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
        )
        now = timezone.now()
        for entry in entries:
            was_active = entry.status == QueueEntry.Status.ACTIVE
            for pair in entry.pairs.select_related("player_1", "player_2").all():
                activity_log.log_pair_event(
                    CourtActivityLog.EventType.PAIR_ENDED, locked_court, entry, pair,
                    reason=CourtActivityLog.Reason.COURT_DROPPED, actor=actor,
                )
            entry.pairs.all().delete()
            entry.status = (
                QueueEntry.Status.COMPLETED if was_active else QueueEntry.Status.CANCELLED
            )
            entry.ended_at = now
            entry.save()
        activity_log.log_court_event(
            CourtActivityLog.EventType.COURT_DROPPED, locked_court, actor=actor
        )


def deactivate_court(court, actor=None):
    drop_court(court, actor=actor)
    court.is_active = False
    court.save()
    activity_log.log_court_event(
        CourtActivityLog.EventType.COURT_DEACTIVATED, court, actor=actor
    )
