import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from courts.tests.factories import future_expiry, make_court, make_user, past_expiry

pytestmark = pytest.mark.django_db


# Row 13: board is public
def test_court_list_requires_no_auth():
    make_court()
    client = APIClient()
    resp = client.get("/api/courts/")
    assert resp.status_code == 200


# Row 14: joining a queue requires auth
def test_create_queue_entry_requires_auth():
    court = make_court()
    client = APIClient()
    resp = client.post("/api/queue-entries/", {"court_id": court.id, "usernames": ["alice", "bob"]})
    assert resp.status_code in (401, 403)


# Row 16: expired account cannot log in
def test_login_rejected_for_expired_account():
    make_user("alice", expires_at=past_expiry())
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert resp.status_code == 403


# Row 17: a still-valid token stops working once the account expires
def test_expired_account_token_rejected_on_protected_endpoint():
    alice = make_user("alice", expires_at=past_expiry())
    token = Token.objects.create(user=alice)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    resp = client.get("/api/me/status/")
    assert resp.status_code == 403


# Row 18: non-expired account can log in and join a queue
def test_valid_account_can_login_and_join():
    court = make_court()
    make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    client = APIClient()
    login_resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert login_resp.status_code == 200
    token = login_resp.data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    resp = client.post("/api/queue-entries/", {"court_id": court.id, "usernames": ["alice", "bob"]})
    assert resp.status_code == 201
    assert resp.data["status"] == "active"
