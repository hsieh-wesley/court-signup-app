import pytest
from rest_framework.test import APIClient

from courts import services
from courts.models import CourtActivityLog, QueueEntry
from courts.tests.factories import credential, make_court, make_user

pytestmark = pytest.mark.django_db


# Row 5: both correct credentials unsign the shared pair, same as unsign_pair
def test_quick_unsign_ends_shared_pair():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "completed"
    entry.refresh_from_db()
    assert entry.pairs.count() == 0
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ENDED,
        reason=CourtActivityLog.Reason.UNSIGNED,
    ).count() == 1


# Row 6: wrong password for either player rejects, nothing changes
def test_quick_unsign_rejects_wrong_password():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [[credential("alice"), credential("bob", password="wrong")]]},
        format="json",
    )
    assert resp.status_code == 400
    assert QueueEntry.objects.get().pairs.count() == 1


# Row 7: two real accounts who aren't currently paired together
def test_quick_unsign_rejects_when_not_paired_together():
    make_user("alice")
    make_user("bob")

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 400
    assert "aren't signed up together" in resp.data["detail"]


def test_quick_unsign_order_independent():
    """Works regardless of which of the two usernames is player_1/player_2."""
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [[credential("bob"), credential("alice")]]},
        format="json",
    )
    assert resp.status_code == 200


def test_quick_unsign_finds_pair_from_two_pair_entry():
    """Only unsigns the pair the two of them actually share, not the whole entry."""
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 200
    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.pairs.count() == 1
    remaining = entry.pairs.first()
    assert {remaining.player_1.username, remaining.player_2.username} == {"carol", "dave"}


# DoD I: both pairs of a 4-player group unsign together atomically
def test_quick_unsign_four_players_same_entry_ends_it():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    make_user("carol")
    make_user("dave")
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [
            [credential("alice"), credential("bob")],
            [credential("carol"), credential("dave")],
        ]},
        format="json",
    )
    assert resp.status_code == 200
    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED  # was active when both pairs ended
    assert entry.pairs.count() == 0


# DoD H: two pairs on the same physical court but different QueueEntry groups
# must be rejected, and nobody removed.
def test_quick_unsign_rejects_pairs_from_different_entries():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    entry_1 = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry_2 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    client = APIClient()
    resp = client.post(
        "/api/pairs/unsign/",
        {"pairs": [
            [credential("alice"), credential("bob")],
            [credential("carol"), credential("dave")],
        ]},
        format="json",
    )
    assert resp.status_code == 400
    assert "aren't signed up as the same group" in resp.data["detail"]
    entry_1.refresh_from_db()
    entry_2.refresh_from_db()
    assert entry_1.pairs.count() == 1
    assert entry_2.pairs.count() == 1


# Row 1 (service-layer confirmation): 4 players on an empty court share one timer
def test_four_players_on_empty_court_share_one_expiry():
    court = make_court()
    make_user("alice")
    make_user("bob")
    make_user("carol")
    make_user("dave")

    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": court.id,
            "pairs": [
                [credential("alice"), credential("bob")],
                [credential("carol"), credential("dave")],
            ],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["status"] == "active"
    assert len(resp.data["pairs"]) == 2
    assert resp.data["expires_at"] is not None
