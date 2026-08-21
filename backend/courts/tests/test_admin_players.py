import pytest

from courts import activity_log, admin_services, services
from courts.models import LoginLog, Player, QueueEntry
from courts.tests.factories import authed_client, make_admin_user, make_court, make_user

pytestmark = pytest.mark.django_db


def _status_for(client, location_id, username):
    resp = client.get(f"/api/admin/players/?location_id={location_id}")
    assert resp.status_code == 200
    row = next(r for r in resp.data if r["username"] == username)
    return row


# DoD G: no check-in/registration/assignment today -> Not Checked In
def test_status_not_checked_in_by_default():
    court = make_court()
    make_user("alice")
    admin = make_admin_user()
    client = authed_client(admin)

    row = _status_for(client, court.location_id, "alice")
    assert row["status"] == "not_checked_in"
    assert row["court_number"] is None
    assert row["checked_in_at"] is None


# DoD A: explicit check-in -> Waiting Room, with a checked_in_at timestamp
def test_status_waiting_room_after_check_in():
    court = make_court()
    alice = make_user("alice")
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.CHECK_IN)
    admin = make_admin_user()
    client = authed_client(admin)

    row = _status_for(client, court.location_id, "alice")
    assert row["status"] == "waiting_room"
    assert row["checked_in_at"] is not None


# DoD C: signing onto an empty court -> On Court, with the court number surfaced
def test_status_on_court_after_sign_up():
    court = make_court(number=3)
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    admin = make_admin_user()
    client = authed_client(admin)

    row = _status_for(client, court.location_id, "alice")
    assert row["status"] == "on_court"
    assert row["court_number"] == 3


# DoD B2: "Join this pair" fills an existing WAITING entry's open slot
# (distinct from "Sign Up", which would create a brand new queued entry).
def test_status_in_queue_after_joining_open_slot():
    court = make_court(number=5)
    alice = make_user("alice")
    make_user("bob")
    make_user("erin")
    make_user("frank")
    carol = make_user("carol")
    make_user("george")
    hank = make_user("hank")
    make_user("iris")

    # Fill the court with a full 4-player entry so the next one queues.
    services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["erin", "frank"]], created_by=alice
    )
    # A single pair queues behind it, leaving its second slot open.
    entry = services.create_queue_entry(court=court, pairs=[["carol", "george"]], created_by=carol)
    assert entry.status == QueueEntry.Status.WAITING
    # Join this pair: Hank + Iris fill that open slot on the SAME entry.
    services.join_open_slot(entry=entry, usernames=["hank", "iris"], requesting_user=hank)

    admin = make_admin_user()
    client = authed_client(admin)

    row = _status_for(client, court.location_id, "hank")
    assert row["status"] == "in_queue"
    assert row["court_number"] == 5


# DoD E/F: falling off a court/queue returns to Waiting Room, not Not Checked
# In — the check-in row from earlier that day is untouched by unsign.
def test_status_returns_to_waiting_room_after_unsign():
    court = make_court()
    alice = make_user("alice")
    bob = make_user("bob")
    # Presence for the day (in production this is stamped implicitly by
    # verify_pair_credentials on the real Sign Up/Join views — bypassed
    # here since we're calling the service layer directly).
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.CHECK_IN)
    activity_log.log_player_auth_event(bob, court.location, LoginLog.Context.CHECK_IN)
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    services.unsign_by_credentials([[
        {"username": "alice", "password": "pw12345"},
        {"username": "bob", "password": "pw12345"},
    ]])
    admin = make_admin_user()
    client = authed_client(admin)

    row = _status_for(client, court.location_id, "alice")
    assert row["status"] == "waiting_room"


# DoD N: the Locations table's aggregate counts match the Users list.
def test_location_counts_match_player_statuses():
    court = make_court(number=1)
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    erin = make_user("erin")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    activity_log.log_player_auth_event(erin, court.location, LoginLog.Context.CHECK_IN)
    court2 = make_court(location=court.location, number=2)
    services.create_queue_entry(court=court2, pairs=[["carol", "dave"]], created_by=carol)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/locations/")
    assert resp.status_code == 200
    row = next(r for r in resp.data if r["id"] == court.location_id)
    assert row["on_court_count"] == 4  # alice, bob, carol, dave all promoted onto empty courts
    assert row["in_queue_count"] == 0
    assert row["waiting_room_count"] == 1  # erin only


# No persisted plaintext password anywhere: reset/add-login return a
# fresh password once, invalidate the old one, and nothing about it is
# retrievable afterward -- only Django's hash is ever stored.
def test_reset_password_invalidates_the_old_one_and_returns_a_fresh_one():
    player, first = admin_services.create_player("Alice", username="alice", enable_login=True)
    assert services.verify_credential("alice", first)

    second = admin_services.reset_password(player)

    assert second != first
    with pytest.raises(services.ServiceError):
        services.verify_credential("alice", first)
    assert services.verify_credential("alice", second)


def test_add_login_returns_a_fresh_password_each_call():
    player, _ = admin_services.create_player("Alice", enable_login=False)
    first = admin_services.add_login(player, "alice")
    assert services.verify_credential("alice", first)

    second = admin_services.add_login(player, "alice")
    assert second != first
    with pytest.raises(services.ServiceError):
        services.verify_credential("alice", first)
    assert services.verify_credential("alice", second)


def test_admin_players_endpoint_never_exposes_a_password_field():
    admin_services.create_player("Alice", username="alice", enable_login=True)

    for is_superuser in (False, True):
        client = authed_client(make_admin_user(f"acct{is_superuser}", is_superuser=is_superuser))
        resp = client.get("/api/admin/players/")
        assert resp.status_code == 200
        row = next(r for r in resp.data if r["username"] == "alice")
        assert "password" not in row


def test_create_player_response_reveals_password_once():
    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(
        "/api/admin/players/",
        {"display_name": "Grace", "username": "grace", "enable_login": True},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["password"]

    # But a later fetch of the same player never exposes it again.
    resp2 = client.get("/api/admin/players/")
    row = next(r for r in resp2.data if r["username"] == "grace")
    assert "password" not in row


# Delete Player: only a non-member with zero court/queue activity is
# eligible; even then it truly deletes the account (and its LoginLog
# rows -- non-member identity isn't preserved long-term, unlike every
# other delete in this app).
def test_delete_player_removes_fresh_non_member_account_and_its_login_log():
    player, _plaintext = admin_services.create_player("Guest", username="guest", enable_login=True)
    activity_log.log_player_auth_event(player.user, None, LoginLog.Context.REGISTRATION)
    assert LoginLog.objects.filter(username="guest").exists()
    player_id = player.id
    user_id = player.user_id

    admin_services.delete_player(player)

    assert not Player.objects.filter(id=player_id).exists()
    from django.contrib.auth import get_user_model

    assert not get_user_model().objects.filter(id=user_id).exists()
    assert not LoginLog.objects.filter(username="guest").exists()


def test_delete_player_refuses_a_member():
    _player, membership, _plaintext = admin_services.start_membership("kate", "5551230099")
    with pytest.raises(services.ServiceError, match="membership"):
        admin_services.delete_player(membership.player)
    assert Player.objects.filter(id=membership.player_id).exists()


def test_delete_player_refuses_someone_with_court_activity():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    player = Player.objects.get(user=alice)

    with pytest.raises(services.ServiceError, match="play history"):
        admin_services.delete_player(player)
    assert Player.objects.filter(id=player.id).exists()


def test_player_can_delete_is_false_once_membership_or_activity_exists():
    fresh, _plaintext = admin_services.create_player("Guest", username="guesttwo", enable_login=True)
    assert admin_services.player_can_delete(fresh) is True

    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    played = Player.objects.get(user=alice)
    assert admin_services.player_can_delete(played) is False


def test_staff_cannot_delete_player_but_admin_can():
    player, _plaintext = admin_services.create_player("Guest", username="guestthree", enable_login=True)

    staff = make_admin_user("staff", is_superuser=False)
    staff_client = authed_client(staff)
    resp = staff_client.post(f"/api/admin/players/{player.id}/delete/")
    assert resp.status_code == 403
    assert Player.objects.filter(id=player.id).exists()

    admin = make_admin_user("admin")
    admin_client = authed_client(admin)
    resp = admin_client.post(f"/api/admin/players/{player.id}/delete/")
    assert resp.status_code == 204
    assert not Player.objects.filter(id=player.id).exists()


def test_admin_delete_endpoint_refuses_member_with_409():
    _player, membership, _plaintext = admin_services.start_membership("kate", "5551230099")
    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(f"/api/admin/players/{membership.player_id}/delete/")
    assert resp.status_code == 409
    assert Player.objects.filter(id=membership.player_id).exists()


def test_admin_players_endpoint_exposes_can_delete():
    fresh, _plaintext = admin_services.create_player("Guest", username="guestfour", enable_login=True)
    _player, membership, _plaintext2 = admin_services.start_membership("kate", "5551230099")

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/players/")
    row_guest = next(r for r in resp.data if r["username"] == "guestfour")
    row_member = next(r for r in resp.data if r["username"] == "kate")
    assert row_guest["can_delete"] is True
    assert row_member["can_delete"] is False
