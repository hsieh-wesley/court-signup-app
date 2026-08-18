from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import Court, Pair, Player, QueueEntry
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
        Token.objects.filter(user=user).delete()
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
    Token.objects.filter(user=player.user).delete()


def reset_password(player):
    if player.user is None:
        raise ServiceError("This player has no login access.")
    plaintext = generate_password()
    player.user.set_password(plaintext)
    player.user.save()
    Token.objects.filter(user=player.user).delete()
    return plaintext


def _remove_all_pairs_for_user(user):
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
            _end_pair(locked_court, locked_entry, locked_pair)


def deactivate_player(player):
    """Archives the player and, if they have login, disables it too and
    clears any current court/queue assignment. The Player row itself is
    never deleted (Pair/QueueEntry rows have PROTECT FKs to auth.User, so
    hard-deleting anyone with play history isn't possible without a bigger
    migration — archiving is the supported path)."""
    if player.user is not None:
        _remove_all_pairs_for_user(player.user)
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
            Token.objects.filter(user=user).delete()
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


def create_court(name, capacity=None):
    if Court.objects.filter(name=name).exists():
        raise ServiceError(f"A court named '{name}' already exists.")
    kwargs = {"name": name}
    if capacity is not None:
        kwargs["capacity"] = capacity
    return Court.objects.create(**kwargs)


def remove_player_from_court(court, username):
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
        _end_pair(locked_court, locked_entry, pair)


def drop_court(court):
    """Ends every active/waiting entry on this court in one shot. No
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
            entry.pairs.all().delete()
            entry.status = (
                QueueEntry.Status.COMPLETED if was_active else QueueEntry.Status.CANCELLED
            )
            entry.ended_at = now
            entry.save()


def deactivate_court(court):
    drop_court(court)
    court.is_active = False
    court.save()
