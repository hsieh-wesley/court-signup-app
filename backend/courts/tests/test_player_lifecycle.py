import pytest
from django.contrib.auth import authenticate

from courts import admin_services, services
from courts.models import Player, PlayerSession, QueueEntry
from courts.tests.factories import default_location, make_court, make_user, pair_for

pytestmark = pytest.mark.django_db


# Row 2: a player can exist with no login access at all
def test_create_player_without_login():
    player, plaintext = admin_services.create_player(display_name="Grace", enable_login=False)
    assert player.has_login is False
    assert plaintext is None
    assert player.user is None


# Row 3: creating with login generates a password and a real account
def test_create_player_with_login_generates_password():
    player, plaintext = admin_services.create_player(
        display_name="Grace", username="grace", enable_login=True
    )
    assert player.has_login is True
    assert plaintext is not None
    assert authenticate(username="grace", password=plaintext) is not None


def test_create_player_enable_login_requires_username():
    with pytest.raises(services.ServiceError):
        admin_services.create_player(display_name="Grace", enable_login=True)


def test_create_player_rejects_taken_username():
    make_user("grace")
    with pytest.raises(services.ServiceError):
        admin_services.create_player(display_name="Grace 2", username="grace", enable_login=True)


# Row 4: reset invalidates the old password and the old session
def test_reset_password_invalidates_old_password_and_session():
    user = make_user("grace")
    old_session = PlayerSession.objects.create(user=user, location=default_location())
    player = user.player

    new_plaintext = admin_services.reset_password(player)

    assert authenticate(username="grace", password="pw12345") is None
    assert authenticate(username="grace", password=new_plaintext) is not None
    assert not PlayerSession.objects.filter(pk=old_session.pk).exists()


# Row 5: disabling login blocks auth but leaves the player record active
def test_disable_login_blocks_auth_but_keeps_player_active():
    user = make_user("grace")
    PlayerSession.objects.create(user=user, location=default_location())
    player = user.player

    admin_services.disable_login(player)

    user.refresh_from_db()
    player.refresh_from_db()
    assert user.is_active is False
    assert authenticate(username="grace", password="pw12345") is None
    assert player.is_active is True
    assert PlayerSession.objects.filter(user=user).count() == 0


# Row 6: re-adding login reuses the same User row and issues a fresh password
def test_add_login_after_disable_reuses_same_user_row():
    user = make_user("grace")
    player = user.player
    admin_services.disable_login(player)

    new_plaintext = admin_services.add_login(player, "grace")

    player.refresh_from_db()
    user.refresh_from_db()
    assert player.user_id == user.id
    assert user.is_active is True
    assert authenticate(username="grace", password=new_plaintext) is not None


def test_add_login_rejects_taken_username():
    make_user("grace")
    player, _ = admin_services.create_player(display_name="Heidi", enable_login=False)
    with pytest.raises(services.ServiceError):
        admin_services.add_login(player, "grace")


# Row 7: deactivating a player who's currently on a court ends their pair
# and lets the next queued entry get promoted, same as a normal unsign.
def test_deactivate_player_removes_current_court_assignment():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    waiting = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )

    admin_services.deactivate_player(alice.player)

    active.refresh_from_db()
    waiting.refresh_from_db()
    alice.refresh_from_db()
    alice.player.refresh_from_db()

    assert active.status == QueueEntry.Status.COMPLETED
    assert waiting.status == QueueEntry.Status.ACTIVE
    assert alice.is_active is False
    assert alice.player.is_active is False


def test_deactivate_player_without_login_just_archives():
    player, _ = admin_services.create_player(display_name="Grace", enable_login=False)
    admin_services.deactivate_player(player)
    player.refresh_from_db()
    assert player.is_active is False


def test_edit_player_display_name_and_username():
    user = make_user("grace")
    player = user.player

    admin_services.edit_player(player, display_name="Gracie", username="gracie")

    player.refresh_from_db()
    user.refresh_from_db()
    assert player.display_name == "Gracie"
    assert user.username == "gracie"


def test_edit_player_username_without_login_rejected():
    player, _ = admin_services.create_player(display_name="Grace", enable_login=False)
    with pytest.raises(services.ServiceError):
        admin_services.edit_player(player, username="grace")


# Row 14: bulk test-player creation is idempotent
def test_create_test_players_idempotent():
    first = admin_services.create_test_players(8)
    assert len(first) == 8
    assert Player.objects.filter(display_name__startswith="Player ").count() == 8

    second = admin_services.create_test_players(8)
    assert len(second) == 8
    assert Player.objects.filter(display_name__startswith="Player ").count() == 8
    # Passwords are regenerated, not reused.
    first_by_username = {r["username"]: r["password"] for r in first}
    for r in second:
        assert r["password"] != first_by_username[r["username"]]
