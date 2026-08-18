from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from . import activity_log
from .models import Court, CourtActivityLog, Location, Pair, Player, PlayerSession, QueueEntry
from .password_gen import generate_password, generate_unique_passwords
from .services import ServiceError, _end_pair

User = get_user_model()


def create_player(display_name, username=None, enable_login=False):
    """Returns (player, plaintext_password_or_None)."""
    if not display_name:
        raise ServiceError("display_name is required.")
    if enable_login and not username:
        raise ServiceError("username is required when enable_login is true.")
    if username and User.objects.filter(username=username).exists():
        raise ServiceError(f"Username '{username}' is already taken.")

    with transaction.atomic():
        plaintext = None
        user = None
        if enable_login:
            plaintext = generate_password()
            user = User.objects.create_user(username=username, password=plaintext)
        player = Player.objects.create(display_name=display_name, user=user)

    return player, plaintext


def edit_player(player, display_name=None, username=None):
    if display_name is not None:
        player.display_name = display_name
    if username is not None:
        if player.user is None:
            raise ServiceError("This player has no login access to rename.")
        if User.objects.exclude(pk=player.user_id).filter(username=username).exists():
            raise ServiceError(f"Username '{username}' is already taken.")
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
        if username != user.username and User.objects.exclude(pk=user.pk).filter(
            username=username
        ).exists():
            raise ServiceError(f"Username '{username}' is already taken.")
        user.username = username
        user.is_active = True
        plaintext = generate_password()
        user.set_password(plaintext)
        user.save()
        PlayerSession.objects.filter(user=user).delete()
        return plaintext

    if User.objects.filter(username=username).exists():
        raise ServiceError(f"Username '{username}' is already taken.")
    plaintext = generate_password()
    user = User.objects.create_user(username=username, password=plaintext)
    player.user = user
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
                player = Player.objects.create(user=user, display_name=display_name)
            else:
                player.is_active = True
                player.display_name = display_name
                player.save()
        except User.DoesNotExist:
            user = User.objects.create_user(username=username, password=plaintext)
            Player.objects.create(user=user, display_name=display_name)
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
