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


# Admins get a real, persisted session + an ADMIN_LOGIN history row.
def test_admin_login_creates_session_and_login_log():
    court = make_court()
    admin = make_admin_user()
    session = services.create_player_session(admin, court.location)
    assert session.location_id == court.location_id
    assert (
        LoginLog.objects.filter(
            user=admin, location=court.location, context=LoginLog.Context.ADMIN_LOGIN
        ).count()
        == 1
    )


# Regular players never get a persistent session under the public-kiosk model.
def test_create_player_session_rejects_non_staff():
    alice = make_user("alice")
    with pytest.raises(services.ServiceError):
        services.create_player_session(alice, make_court().location)
    assert PlayerSession.objects.filter(user=alice).count() == 0


# Admins may hold multiple concurrent sessions — no single-session limit.
def test_admin_can_hold_sessions_at_multiple_facilities():
    loc_a = make_court().location
    loc_b = make_location("Other")
    admin = make_admin_user()

    services.create_player_session(admin, loc_a)
    services.create_player_session(admin, loc_b)

    assert PlayerSession.objects.filter(user=admin).count() == 2


# The cross-facility conflict check moved from login-time to join-time.
def test_verify_pair_credentials_rejects_player_active_at_another_facility():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    alice = make_user("alice")
    bob = make_user("bob")
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)

    other_court = make_court(location=other, number=1)
    with pytest.raises(services.ServiceError) as exc_info:
        services.verify_pair_credentials(
            [[{"username": "alice", "password": "pw12345"},
              {"username": "carol", "password": "pw12345"}]],
            other_court.location,
        )
    assert exc_info.value.status == 409
    # Nothing about her original pair changed.
    home_entry = alice.pairs_as_player1.first().entry
    assert home_entry.status == "active"


def test_verify_pair_credentials_allows_waiting_pair_same_facility():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    # Re-verifying alice for the SAME facility is never blocked by her own presence.
    services.verify_pair_credentials(
        [[{"username": "alice", "password": "pw12345"},
          {"username": "bob", "password": "pw12345"}]],
        court.location,
    )


# reset_password still invalidates any (rare/stale) PlayerSession rows.
def test_reset_password_invalidates_all_sessions_everywhere():
    loc_a = make_court().location
    loc_b = make_location("Other")
    alice = make_user("alice")
    PlayerSession.objects.create(user=alice, location=loc_a)
    PlayerSession.objects.create(user=alice, location=loc_b)
    assert PlayerSession.objects.filter(user=alice).count() == 2

    admin_services.reset_password(alice.player)

    assert PlayerSession.objects.filter(user=alice).count() == 0


# API-level: admin logout only deletes the current session.
def test_logout_only_deletes_current_session():
    admin = make_admin_user()
    client = authed_client(admin)
    other_session = PlayerSession.objects.create(user=admin, location=make_location("Other"))

    resp = client.post("/api/auth/logout/")
    assert resp.status_code == 204
    assert PlayerSession.objects.filter(pk=other_session.pk).exists()


def test_join_endpoint_returns_409_with_clear_message_naming_the_facility():
    home = make_court()
    other = make_location("UCLA Recreation Center")
    other_court = make_court(location=other, number=1)
    alice = make_user("alice")
    make_user("bob")
    make_user("carol")
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": other_court.id,
            "pairs": [[
                {"username": "alice", "password": "pw12345"},
                {"username": "carol", "password": "pw12345"},
            ]],
        },
        format="json",
    )
    assert resp.status_code == 409
    assert home.location.name in resp.data["detail"]
    assert str(home.number) in resp.data["detail"]


def test_login_endpoint_rejects_non_staff():
    make_user("alice")
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert resp.status_code == 400
