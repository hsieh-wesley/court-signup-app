import pytest

from courts import activity_log, admin_services, services
from courts.models import LoginLog
from courts.tests.factories import (
    authed_client,
    make_admin_user,
    make_court,
    make_location,
    make_user,
)

pytestmark = pytest.mark.django_db


def test_admin_login_history_lists_logins():
    court = make_court()
    alice = make_user("alice")
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.STATUS_CHECK)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/history/logins/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["username"] == "alice"
    assert resp.data[0]["context"] == "status_check"
    assert "password" not in resp.data[0]
    assert "token" not in resp.data[0]


def test_admin_login_history_filters_by_location():
    court = make_court()
    other = make_location("Other")
    alice = make_user("alice")
    bob = make_user("bob")
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.STATUS_CHECK)
    activity_log.log_player_auth_event(bob, other, LoginLog.Context.REGISTRATION)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get(f"/api/admin/history/logins/?location_id={court.location_id}")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["username"] == "alice"


def test_admin_login_history_filters_by_context():
    court = make_court()
    alice = make_user("alice")
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.STATUS_CHECK)
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.REGISTRATION)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/history/logins/?context=registration")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["context"] == "registration"


def test_admin_court_activity_history_lists_events():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/history/court-activity/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["event_type"] == "pair_activated"
    assert resp.data[0]["player_1_username"] == "alice"


def test_admin_court_activity_history_filters_by_event_type():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    admin_services.drop_court(court)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.get("/api/admin/history/court-activity/?event_type=court_dropped")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["event_type"] == "court_dropped"


def test_normal_player_forbidden_from_history():
    alice = make_user("alice")
    client = authed_client(alice)
    resp = client.get("/api/admin/history/logins/")
    assert resp.status_code == 403
    resp = client.get("/api/admin/history/court-activity/")
    assert resp.status_code == 403
