import pytest

from courts import admin_services, services
from courts.models import QueueEntry
from courts.tests.factories import authed_client, make_admin_user, make_court, make_user

pytestmark = pytest.mark.django_db


# Row 11: removing one player ends just their pair; entry survives if another remains
def test_remove_player_from_court_ends_only_their_pair():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    make_user("carol")
    make_user("dave")

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )
    assert entry.status == QueueEntry.Status.ACTIVE

    admin_services.remove_player_from_court(court, "alice")

    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.pairs.count() == 1
    remaining = entry.pairs.first()
    assert {remaining.player_1.username, remaining.player_2.username} == {"carol", "dave"}


def test_remove_player_from_court_promotes_next_when_last_pair_removed():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    waiting = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )

    admin_services.remove_player_from_court(court, "alice")

    active.refresh_from_db()
    waiting.refresh_from_db()
    assert active.status == QueueEntry.Status.COMPLETED
    assert waiting.status == QueueEntry.Status.ACTIVE


def test_remove_player_not_on_court_rejected():
    court = make_court()
    make_user("alice")
    with pytest.raises(services.ServiceError):
        admin_services.remove_player_from_court(court, "alice")


# Row 12: dropping a court ends every entry, court stays available
def test_drop_court_ends_everything_and_stays_available():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    eve = make_user("eve")
    make_user("frank")

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    waiting1 = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )
    waiting2 = services.create_queue_entry(court=court, pairs=[["eve", "frank"]], created_by=eve)

    admin_services.drop_court(court)

    active.refresh_from_db()
    waiting1.refresh_from_db()
    waiting2.refresh_from_db()
    court.refresh_from_db()

    assert active.status == QueueEntry.Status.COMPLETED
    assert waiting1.status == QueueEntry.Status.CANCELLED
    assert waiting2.status == QueueEntry.Status.CANCELLED
    assert court.is_active is True

    # Everyone is free to rejoin immediately.
    rejoined = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    assert rejoined.status == QueueEntry.Status.ACTIVE


# Row 13: deactivating a court blocks new signups
def test_deactivate_court_blocks_new_signups():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")

    admin_services.deactivate_court(court)
    court.refresh_from_db()
    assert court.is_active is False

    with pytest.raises(services.ServiceError):
        services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)


def test_deactivate_court_clears_current_players_first():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin_services.deactivate_court(court)

    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED


def test_create_court_rejects_duplicate_name():
    make_court("Court 9")
    with pytest.raises(services.ServiceError):
        admin_services.create_court("Court 9")


# API-level checks for the same behaviors, via an admin-authenticated client
def test_admin_api_drop_court_endpoint():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(f"/api/admin/courts/{court.id}/drop/")
    assert resp.status_code == 204

    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED


def test_admin_api_remove_player_endpoint():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(f"/api/admin/courts/{court.id}/remove-player/", {"username": "alice"})
    assert resp.status_code == 204

    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED
