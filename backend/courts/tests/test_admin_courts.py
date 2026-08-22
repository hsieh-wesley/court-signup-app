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


def test_create_court_rejects_duplicate_number_at_same_location():
    court = make_court()
    with pytest.raises(services.ServiceError):
        admin_services.create_court(court.location, number=court.number)


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


# Admin add/move/remove without passwords.
def test_add_group_to_court_signs_up_a_pair_no_password_needed():
    court = make_court()
    make_user("alice")
    make_user("bob")
    admin_services.add_group_to_court(court, ["alice", "bob"])

    entry = QueueEntry.objects.get(court=court)
    assert entry.status == QueueEntry.Status.ACTIVE
    usernames = {p.player_1.username for p in entry.pairs.all()} | {
        p.player_2.username for p in entry.pairs.all()
    }
    assert usernames == {"alice", "bob"}


def test_add_group_to_court_rejects_wrong_group_size():
    court = make_court()
    make_user("alice")
    with pytest.raises(services.ServiceError, match="2 or 4"):
        admin_services.add_group_to_court(court, ["alice"])


def test_add_group_to_court_rejects_unknown_username():
    court = make_court()
    make_user("alice")
    with pytest.raises(services.ServiceError, match="Unknown username"):
        admin_services.add_group_to_court(court, ["alice", "ghost"])


def test_add_group_to_court_rejects_player_active_elsewhere():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    make_user("carol")

    with pytest.raises(services.ServiceError, match="still signed in"):
        admin_services.add_group_to_court(court2, ["alice", "carol"])


def test_add_pair_to_open_slot_fills_the_second_slot_no_password_needed():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    make_user("erin")
    make_user("frank")
    admin_services.add_pair_to_open_slot(entry, ["erin", "frank"])
    entry.refresh_from_db()
    assert entry.pairs.count() == 2
    all_usernames = {u for p in entry.pairs.all() for u in (p.player_1.username, p.player_2.username)}
    assert all_usernames == {"carol", "dave", "erin", "frank"}


def test_move_entry_to_court_preserves_active_timer():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    assert entry.status == QueueEntry.Status.ACTIVE
    original_expires_at = entry.expires_at

    moved = admin_services.move_entry_to_court(entry, court2)
    assert moved.court_id == court2.id
    assert moved.status == QueueEntry.Status.ACTIVE
    assert moved.expires_at == original_expires_at


def test_move_entry_to_court_promotes_the_origin_courts_own_queue():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    carol = make_user("carol")
    make_user("dave")
    waiting = services.create_queue_entry(court=court1, pairs=[["carol", "dave"]], created_by=carol)
    assert waiting.status == QueueEntry.Status.WAITING

    admin_services.move_entry_to_court(entry, court2)
    waiting.refresh_from_db()
    assert waiting.status == QueueEntry.Status.ACTIVE  # promoted onto the now-empty court1


def test_move_entry_to_court_refuses_target_with_its_own_active_group():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    carol = make_user("carol")
    make_user("dave")
    services.create_queue_entry(court=court2, pairs=[["carol", "dave"]], created_by=carol)

    with pytest.raises(services.ServiceError, match="already has an active group"):
        admin_services.move_entry_to_court(entry, court2)


def test_move_entry_to_court_refuses_conflicting_usernames_on_target():
    # Under normal flows a player can never be on two courts at once
    # (_reject_if_active_elsewhere already prevents it), so this
    # exercises move_entry_to_court's own defensive _conflicting_usernames
    # check directly, by constructing the conflict at the ORM level.
    from courts.models import Pair

    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    carol = make_user("carol")
    other_entry = QueueEntry.objects.create(court=court2, created_by=carol, status=QueueEntry.Status.WAITING)
    Pair.objects.create(entry=other_entry, slot=1, player_1=carol, player_2=alice, created_by=carol)

    with pytest.raises(services.ServiceError, match="Already signed up"):
        admin_services.move_entry_to_court(entry, court2)


# API-level checks for add/join/move, admin-authenticated, no passwords sent.
def test_admin_api_add_group_endpoint():
    court = make_court()
    make_user("alice")
    make_user("bob")
    admin = make_admin_user()
    client = authed_client(admin)

    resp = client.post(f"/api/admin/courts/{court.id}/add-group/", {"usernames": ["alice", "bob"]})
    assert resp.status_code == 204
    entry = QueueEntry.objects.get(court=court)
    assert entry.status == QueueEntry.Status.ACTIVE


def test_admin_api_join_open_slot_endpoint():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    make_user("erin")
    make_user("frank")

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(
        f"/api/admin/courts/entries/{entry.id}/join-open-slot/", {"usernames": ["erin", "frank"]}
    )
    assert resp.status_code == 204
    entry.refresh_from_db()
    assert entry.pairs.count() == 2


def test_admin_api_move_entry_endpoint():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)

    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post(
        f"/api/admin/courts/entries/{entry.id}/move/", {"target_court_id": court2.id}
    )
    assert resp.status_code == 204
    entry.refresh_from_db()
    assert entry.court_id == court2.id


def test_staff_can_use_add_move_remove_court_actions():
    court1 = make_court(number=1)
    court2 = make_court(location=court1.location, number=2)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)

    staff = make_admin_user("staff", is_superuser=False)
    client = authed_client(staff)
    resp = client.post(
        f"/api/admin/courts/entries/{entry.id}/move/", {"target_court_id": court2.id}
    )
    assert resp.status_code == 204
