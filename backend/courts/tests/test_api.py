import pytest
from rest_framework.test import APIClient

from courts import services
from courts.tests.factories import (
    authed_client,
    credential,
    future_expiry,
    make_admin_user,
    make_court,
    make_location,
    make_user,
    past_expiry,
)

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
    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code in (401, 403)


# Row 16: expired account cannot log in
def test_login_rejected_for_expired_account():
    make_user("alice", expires_at=past_expiry())
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert resp.status_code == 403


# Row 17: a still-valid session stops working once the account expires
def test_expired_account_session_rejected_on_protected_endpoint():
    alice = make_user("alice", expires_at=past_expiry())
    client = authed_client(alice)
    resp = client.get("/api/me/status/")
    assert resp.status_code == 403


# Row 18: non-expired account can log in and join a queue
def test_valid_account_can_login_and_join():
    court = make_court()
    make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "pw12345", "location_id": court.location_id},
    )
    assert login_resp.status_code == 200
    token = login_resp.data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": court.id,
            "pairs": [[credential("alice"), credential("bob")]],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["status"] == "active"


def test_login_requires_location_for_regular_player():
    make_user("alice", expires_at=future_expiry())
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "alice", "password": "pw12345"})
    assert resp.status_code == 400


def test_login_does_not_require_location_for_admin():
    make_admin_user("boss")
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "boss", "password": "pw12345"})
    assert resp.status_code == 200
    assert resp.data["is_staff"] is True


# Row 31: join-open-slot requires auth
def test_join_open_slot_requires_auth():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    client = APIClient()
    resp = client.post(
        f"/api/queue-entries/{entry.id}/join/",
        {"credentials": [credential("carol"), credential("dave")]},
        format="json",
    )
    assert resp.status_code in (401, 403)


# Row 32: authenticated join succeeds and returns both pairs
def test_join_open_slot_succeeds():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = authed_client(eve, location=court.location)
    resp = client.post(
        f"/api/queue-entries/{entry.id}/join/",
        {"credentials": [credential("eve"), credential("frank")]},
        format="json",
    )
    assert resp.status_code == 200
    assert len(resp.data["pairs"]) == 2
    slots = {p["slot"] for p in resp.data["pairs"]}
    assert slots == {1, 2}


def test_join_open_slot_rejects_wrong_partner_password():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = authed_client(eve, location=court.location)
    resp = client.post(
        f"/api/queue-entries/{entry.id}/join/",
        {"credentials": [credential("eve"), credential("frank", password="wrong")]},
        format="json",
    )
    assert resp.status_code == 400
    assert entry.pairs.count() == 1


# Row 33: unsign by pair_id, rejecting a pair_id from a different entry
def test_unsign_by_pair_id():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    entry1 = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry2 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = authed_client(alice, location=court.location)

    other_pair_id = entry2.pairs.get().id
    resp = client.post(
        f"/api/queue-entries/{entry1.id}/unsign/", {"pair_id": other_pair_id}, format="json"
    )
    assert resp.status_code == 400

    own_pair_id = entry1.pairs.get().id
    resp = client.post(
        f"/api/queue-entries/{entry1.id}/unsign/", {"pair_id": own_pair_id}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "completed"


# Row 34: open_slot flag reflects fill state and status
def test_open_slot_flag_on_board():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())
    make_user("grace", expires_at=future_expiry())
    make_user("heidi", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    open_entry = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )
    full_entry = services.create_queue_entry(
        court=court, pairs=[["eve", "frank"], ["grace", "heidi"]], created_by=eve
    )

    client = APIClient()
    resp = client.get("/api/courts/")
    assert resp.status_code == 200
    board = next(c for c in resp.data if c["id"] == court.id)

    active_entry = board["active_entry"]
    assert active_entry["open_slot"] is False

    waiting_by_id = {e["id"]: e for e in board["waiting_entries"]}
    assert waiting_by_id[open_entry.id]["open_slot"] is True
    assert waiting_by_id[full_entry.id]["open_slot"] is False


# Facility-scoping: acting on a court at a different facility is rejected
def test_create_queue_entry_rejects_court_from_different_facility():
    other_location = make_location("UCLA Recreation Center")
    other_court = make_court(location=other_location, number=1)
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())

    home_court = make_court()  # default location, different from other_location
    client = authed_client(alice, location=home_court.location)

    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": other_court.id,
            "pairs": [[credential("alice"), credential("bob")]],
        },
        format="json",
    )
    assert resp.status_code == 403


def test_my_status_only_shows_current_facility_entries():
    home = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    services.create_queue_entry(court=home, pairs=[["alice", "bob"]], created_by=alice)

    other_location = make_location("UCLA Recreation Center")
    other_court = make_court(location=other_location, number=1)
    carol = make_user("carol", expires_at=future_expiry())
    services.create_queue_entry(court=other_court, pairs=[["alice", "carol"]], created_by=alice)

    client = authed_client(alice, location=home.location)
    resp = client.get("/api/me/status/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["court"] == home.name
