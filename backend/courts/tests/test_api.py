import pytest
from rest_framework.test import APIClient

from courts import services
from courts.models import Player
from courts.tests.factories import (
    credential,
    future_expiry,
    make_admin_user,
    make_court,
    make_user,
    past_expiry,
)

pytestmark = pytest.mark.django_db


# Board is public
def test_court_list_requires_no_auth():
    make_court()
    client = APIClient()
    resp = client.get("/api/courts/")
    assert resp.status_code == 200


# Public kiosk model: no token needed, but credentials are still required and verified
def test_create_queue_entry_is_public_but_requires_valid_credentials():
    court = make_court()
    make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": court.id,
            "pairs": [[credential("alice"), credential("bob", password="wrong")]],
        },
        format="json",
    )
    assert resp.status_code == 400


def test_create_queue_entry_succeeds_with_no_token_and_valid_credentials():
    court = make_court()
    make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    client = APIClient()  # deliberately no Authorization header at all
    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["status"] == "active"


def test_expired_player_credentials_rejected_when_joining():
    court = make_court()
    make_user("alice", expires_at=past_expiry())
    make_user("bob", expires_at=future_expiry())
    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 403


def test_login_rejected_for_expired_admin():
    admin = make_admin_user("boss")
    Player.objects.create(user=admin, display_name="boss", expires_at=past_expiry())
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "boss", "password": "pw12345"})
    assert resp.status_code == 403


def test_login_does_not_require_location_for_admin():
    make_admin_user("boss")
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": "boss", "password": "pw12345"})
    assert resp.status_code == 200
    assert resp.data["is_staff"] is True


def test_join_open_slot_is_public_but_requires_valid_credentials():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    client = APIClient()
    resp = client.post(
        f"/api/queue-entries/{entry.id}/join/",
        {"credentials": [credential("carol", password="wrong"), credential("dave")]},
        format="json",
    )
    assert resp.status_code == 400


def test_join_open_slot_succeeds_with_no_token():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = APIClient()
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
    make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = APIClient()
    resp = client.post(
        f"/api/queue-entries/{entry.id}/join/",
        {"credentials": [credential("eve"), credential("frank", password="wrong")]},
        format="json",
    )
    assert resp.status_code == 400
    assert entry.pairs.count() == 1


# Unsign identity now comes from credentials in the body, not a token
def test_unsign_by_pair_id_with_credentials():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    entry1 = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry2 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = APIClient()

    other_pair_id = entry2.pairs.get().id
    resp = client.post(
        f"/api/queue-entries/{entry1.id}/unsign/",
        {"pair_id": other_pair_id, **credential("alice")},
        format="json",
    )
    assert resp.status_code == 400

    own_pair_id = entry1.pairs.get().id
    resp = client.post(
        f"/api/queue-entries/{entry1.id}/unsign/",
        {"pair_id": own_pair_id, **credential("alice")},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "completed"


def test_unsign_rejects_wrong_password():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    pair_id = entry.pairs.get().id

    client = APIClient()
    resp = client.post(
        f"/api/queue-entries/{entry.id}/unsign/",
        {"pair_id": pair_id, **credential("alice", password="wrong")},
        format="json",
    )
    assert resp.status_code == 400
    assert entry.pairs.count() == 1


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


# My Status is now a public POST-with-credentials endpoint, no token
def test_player_status_requires_valid_credentials():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post("/api/me/status/", {**credential("alice", password="wrong")})
    assert resp.status_code == 400


def test_player_status_returns_current_entry():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post("/api/me/status/", {**credential("alice"), "location_id": court.location_id})
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["court"] == court.name


def test_player_status_works_without_location_id():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post("/api/me/status/", credential("alice"))
    assert resp.status_code == 200
    assert len(resp.data) == 1
