import pytest
from rest_framework.test import APIClient

from courts import admin_services, services
from courts.models import LoginLog, PlayerSession
from courts.tests.factories import (
    authed_client,
    make_admin_user,
    make_court,
    make_location,
    make_user,
)

pytestmark = pytest.mark.django_db


# Row 5: successful login creates a session scoped to that facility + a LoginLog row
def test_login_creates_scoped_session_and_login_log():
    court = make_court()
    alice = make_user("alice")
    session = services.create_player_session(alice, court.location)
    assert session.location_id == court.location_id
    assert LoginLog.objects.filter(user=alice, location=court.location).count() == 1


# Row 7/8: an active OR waiting pair elsewhere blocks switching facilities
def test_login_blocked_while_active_elsewhere():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)
    home_session = services.create_player_session(alice, home.location)

    with pytest.raises(services.ServiceError) as exc_info:
        services.create_player_session(alice, other)
    assert exc_info.value.status == 409

    # Her original session and pair are completely untouched.
    assert PlayerSession.objects.filter(pk=home_session.pk).exists()
    home_entry = alice.pairs_as_player1.first().entry
    assert home_entry.status == "active"


def test_login_blocked_while_waiting_elsewhere():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    carol = make_user("carol")
    make_user("dave")
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=home, pairs=[["carol", "dave"]], created_by=carol)  # active
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)  # waiting

    with pytest.raises(services.ServiceError):
        services.create_player_session(alice, other)


# Row 9: once free elsewhere, switching succeeds and invalidates the old session
def test_login_succeeds_and_replaces_prior_session_once_free():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    alice = make_user("alice")

    first_session = services.create_player_session(alice, home.location)
    assert PlayerSession.objects.filter(user=alice).count() == 1

    second_session = services.create_player_session(alice, other)

    assert not PlayerSession.objects.filter(pk=first_session.pk).exists()
    assert PlayerSession.objects.filter(user=alice).count() == 1
    assert second_session.location_id == other.id


# Row 10: re-entering the facility you're already active at is never blocked
def test_login_at_same_facility_never_blocked_by_own_presence():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    session = services.create_player_session(alice, court.location)
    assert session.location_id == court.location_id


# Row 11: reset_password invalidates every session, at every facility
def test_reset_password_invalidates_all_sessions_everywhere():
    loc_a = make_court().location
    loc_b = make_location("Other")
    alice = make_user("alice")
    services.create_player_session(alice, loc_a)
    # Can't hold two sessions for a non-staff user, so simulate a second
    # facility's session the way an admin-invalidation scenario would see it.
    PlayerSession.objects.create(user=alice, location=loc_b)
    assert PlayerSession.objects.filter(user=alice).count() == 2

    admin_services.reset_password(alice.player)

    assert PlayerSession.objects.filter(user=alice).count() == 0


# Row 12: admins are exempt from both the conflict check and single-session limit
def test_admin_can_hold_sessions_at_multiple_facilities():
    loc_a = make_court().location
    loc_b = make_location("Other")
    admin = make_admin_user()

    services.create_player_session(admin, loc_a)
    services.create_player_session(admin, loc_b)

    assert PlayerSession.objects.filter(user=admin).count() == 2


# API-level: logout only deletes the current session
def test_logout_only_deletes_current_session():
    court = make_court()
    alice = make_user("alice")
    client = authed_client(alice, location=court.location)
    other_session = PlayerSession.objects.create(user=alice, location=make_location("Other"))

    resp = client.post("/api/auth/logout/")
    assert resp.status_code == 204
    assert PlayerSession.objects.filter(pk=other_session.pk).exists()


def test_login_endpoint_returns_409_with_clear_message():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    alice = make_user("alice", expires_at=None)
    make_user("bob")
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "pw12345", "location_id": other.id},
    )
    assert resp.status_code == 409
    assert home.location.name in resp.data["detail"]
    assert str(home.number) in resp.data["detail"]
