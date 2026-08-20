import pytest
from rest_framework.test import APIClient

from courts.tests.factories import authed_client, make_admin_user, make_user

pytestmark = pytest.mark.django_db


# Row 8: a normal (non-staff) player cannot reach admin endpoints
def test_normal_player_forbidden_from_admin_players_list():
    user = make_user("alice")
    client = authed_client(user)
    resp = client.get("/api/admin/players/")
    assert resp.status_code == 403


def test_normal_player_forbidden_from_creating_admin_court():
    user = make_user("alice")
    client = authed_client(user)
    resp = client.post("/api/admin/courts/", {"name": "Court X"}, format="json")
    assert resp.status_code == 403


# Row 9: unauthenticated requests are rejected
def test_unauthenticated_forbidden_from_admin_players_list():
    client = APIClient()
    resp = client.get("/api/admin/players/")
    assert resp.status_code in (401, 403)


# Row 10: an admin (is_staff) user can reach admin endpoints
def test_admin_can_list_players():
    admin = make_admin_user()
    make_user("alice")
    client = authed_client(admin)
    resp = client.get("/api/admin/players/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["username"] == "alice"


def test_admin_can_create_player():
    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(
        "/api/admin/players/",
        {"display_name": "Grace", "username": "grace", "enable_login": True},
        format="json",
    )
    assert resp.status_code == 201
    assert "password" in resp.data
    assert resp.data["username"] == "grace"


def test_admin_players_list_exposes_viewable_plaintext_but_never_the_hash():
    """`password` is a deliberate, current-plaintext field (see
    Player.current_password_plaintext) admin/staff can view without a
    reset -- but the underlying auth.User hash must never leak alongside
    it."""
    admin = make_admin_user()
    alice = make_user("alice")
    client = authed_client(admin)
    resp = client.get("/api/admin/players/")
    row = resp.data[0]
    assert row["password"] == "pw12345"  # make_user's known plaintext
    assert row["password"] != alice.password  # never the hashed value
    assert not row["password"].startswith("pbkdf2_")


def test_login_response_reports_is_staff():
    make_admin_user("boss")
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "boss", "password": "pw12345"})
    assert resp.status_code == 200
    assert resp.data["is_staff"] is True


# Regular players don't get persistent sessions at all under the public
# kiosk model — /auth/login/ is admin-only now.
def test_login_rejected_for_normal_player():
    make_user("alice")
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert resp.status_code == 400
