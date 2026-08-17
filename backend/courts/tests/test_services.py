import datetime

import pytest
from django.utils import timezone

from courts import services
from courts.models import QueueEntry
from courts.tests.factories import future_expiry, make_court, make_user, pair_for

pytestmark = pytest.mark.django_db


# Row 1: a pair must have exactly 2 usernames
def test_join_with_single_username_pair_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(court=court, pairs=[["alice"]], created_by=alice)


# Row 2: at most 2 pairs (2 slots) may be submitted at once
def test_join_with_three_pairs_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court,
            pairs=[["alice", "bob"], ["carol", "dave"], ["eve", "frank"]],
            created_by=alice,
        )


# Row 3: join with 1 pair on an empty court activates immediately
def test_join_pair_on_empty_court_activates_immediately():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.expires_at is not None
    assert entry.pairs.count() == 1


# Row 4/5: per-court uniqueness, not global
def test_duplicate_username_rejected_on_same_court():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court, pairs=[["alice", "dave"]], created_by=alice
        )


def test_same_username_allowed_on_different_court():
    court1 = make_court("Court 1")
    court2 = make_court("Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    services.create_queue_entry(court=court1, pairs=[["alice", "bob"]], created_by=alice)
    entry2 = services.create_queue_entry(
        court=court2, pairs=[["alice", "eve"]], created_by=alice
    )
    assert entry2.status == QueueEntry.Status.ACTIVE


# Row 6: FIFO promotion order
def test_fifo_promotion_order():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    frank = make_user("frank", expires_at=future_expiry())

    # Court starts occupied so both new entries queue up.
    active = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    e1 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    e2 = services.create_queue_entry(court=court, pairs=[["eve", "frank"]], created_by=eve)
    assert e1.status == QueueEntry.Status.WAITING
    assert e2.status == QueueEntry.Status.WAITING

    services.unsign_pair(
        active, pair_id=pair_for(active, "alice").id, requesting_user=alice
    )

    e1.refresh_from_db()
    e2.refresh_from_db()
    assert e1.status == QueueEntry.Status.ACTIVE
    assert e2.status == QueueEntry.Status.WAITING


# Row 7: expiry -> reap -> promote
def test_reap_expires_active_and_promotes_next():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    waiting = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    active.expires_at = timezone.now() - datetime.timedelta(minutes=5)
    active.save()

    services.reap_expired_reservations(court_ids=[court.id])

    active.refresh_from_db()
    waiting.refresh_from_db()
    assert active.status == QueueEntry.Status.EXPIRED
    assert waiting.status == QueueEntry.Status.ACTIVE
    assert waiting.expires_at > timezone.now()


# Row 9/10: unsign one pair of two leaves the other active, unsign the last ends + promotes
def test_unsign_one_pair_of_two_leaves_other_active():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )
    original_expiry = entry.expires_at

    updated = services.unsign_pair(
        entry, pair_id=pair_for(entry, "alice").id, requesting_user=bob
    )
    assert updated.status == QueueEntry.Status.ACTIVE
    assert updated.expires_at == original_expiry
    assert updated.pairs.count() == 1
    remaining = updated.pairs.first()
    assert {remaining.player_1.username, remaining.player_2.username} == {"carol", "dave"}


def test_unsign_remaining_pair_ends_entry_and_promotes_next():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    frank = make_user("frank", expires_at=future_expiry())

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )
    waiting = services.create_queue_entry(court=court, pairs=[["eve", "frank"]], created_by=eve)

    services.unsign_pair(entry, pair_id=pair_for(entry, "alice").id, requesting_user=bob)
    entry.refresh_from_db()
    ended = services.unsign_pair(entry, pair_id=pair_for(entry, "carol").id, requesting_user=carol)

    assert ended.status == QueueEntry.Status.COMPLETED
    waiting.refresh_from_db()
    assert waiting.status == QueueEntry.Status.ACTIVE


# Row 11/12: unsigning a pair that isn't part of the entry is rejected
def test_unsign_unknown_pair_id_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    with pytest.raises(services.ServiceError):
        services.unsign_pair(entry, pair_id=999999, requesting_user=alice)


def test_unsign_pair_belonging_to_a_different_entry_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    entry1 = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry2 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    with pytest.raises(services.ServiceError):
        services.unsign_pair(
            entry1, pair_id=pair_for(entry2, "carol").id, requesting_user=alice
        )


# Row 15: resign after full unsign
def test_resign_after_full_unsign():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    services.unsign_pair(entry, pair_id=pair_for(entry, "alice").id, requesting_user=alice)

    new_entry = services.create_queue_entry(
        court=court, pairs=[["alice", "frank"]], created_by=alice
    )
    assert new_entry.status == QueueEntry.Status.ACTIVE


# Row 19: a single pair can be admitted alone (minimum 1 slot-pair)
def test_single_pair_admitted_alone():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.pairs.count() == 1
    assert entry.pairs.first().slot == 1


# Row 20: a second pair joins an open WAITING entry before it's promoted
def test_second_pair_joins_open_slot():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    e = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    assert e.status == QueueEntry.Status.WAITING

    updated = services.join_open_slot(e, usernames=["eve", "frank"], requesting_user=eve)
    assert updated.status == QueueEntry.Status.WAITING
    assert updated.pairs.count() == 2
    slots = {p.slot: {p.player_1.username, p.player_2.username} for p in updated.pairs.all()}
    assert slots == {1: {"carol", "dave"}, 2: {"eve", "frank"}}


# Row 21: joining rejected once the entry is ACTIVE
def test_join_rejected_once_active():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    e = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    services.unsign_pair(active, pair_id=pair_for(active, "alice").id, requesting_user=bob)
    e.refresh_from_db()
    assert e.status == QueueEntry.Status.ACTIVE

    with pytest.raises(services.ServiceError):
        services.join_open_slot(e, usernames=["eve", "frank"], requesting_user=eve)


# Row 22: joining rejected once an entry is already full
def test_join_rejected_once_full():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    grace = make_user("grace", expires_at=future_expiry())
    make_user("heidi", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    f = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )
    services.join_open_slot(f, usernames=["grace", "heidi"], requesting_user=grace)

    with pytest.raises(services.ServiceError):
        services.join_open_slot(f, usernames=["grace", "heidi"], requesting_user=grace)


# Row 23: unsigning one pair from a full WAITING entry reopens the slot
def test_slot_reopens_after_unsign_while_waiting():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    frank = make_user("frank", expires_at=future_expiry())
    grace = make_user("grace", expires_at=future_expiry())
    make_user("heidi", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    f = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    services.join_open_slot(f, usernames=["eve", "frank"], requesting_user=eve)
    assert f.pairs.count() == 2

    services.unsign_pair(f, pair_id=pair_for(f, "eve").id, requesting_user=eve)
    f.refresh_from_db()
    assert f.status == QueueEntry.Status.WAITING
    assert f.pairs.count() == 1

    rejoined = services.join_open_slot(f, usernames=["grace", "heidi"], requesting_user=grace)
    assert rejoined.pairs.count() == 2


# Row 24: slot stays locked once ACTIVE, even after a pair leaves
def test_slot_stays_locked_after_unsign_while_active():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"], ["carol", "dave"]], created_by=alice
    )
    assert entry.status == QueueEntry.Status.ACTIVE

    services.unsign_pair(entry, pair_id=pair_for(entry, "carol").id, requesting_user=carol)
    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.pairs.count() == 1

    with pytest.raises(services.ServiceError):
        services.join_open_slot(entry, usernames=["eve", "frank"], requesting_user=eve)


# Row 25: unsigning the last pair of a WAITING entry cancels it
def test_unsign_last_pair_of_waiting_entry_cancels():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    g = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    ended = services.unsign_pair(g, pair_id=pair_for(g, "carol").id, requesting_user=carol)
    assert ended.status == QueueEntry.Status.CANCELLED
    assert ended.pairs.count() == 0


# Row 26: unsigning the last pair of an active single-pair entry promotes the next
def test_unsign_last_pair_of_active_entry_promotes_next():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    h = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    assert h.status == QueueEntry.Status.WAITING

    services.unsign_pair(active, pair_id=pair_for(active, "alice").id, requesting_user=alice)
    active.refresh_from_db()
    h.refresh_from_db()
    assert active.status == QueueEntry.Status.COMPLETED
    assert h.status == QueueEntry.Status.ACTIVE


# Row 27: FIFO promotion by created_at ignores fullness
def test_single_pair_entry_promoted_ahead_of_later_full_entry():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())
    make_user("grace", expires_at=future_expiry())
    make_user("heidi", expires_at=future_expiry())

    active = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    e1 = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    e2 = services.create_queue_entry(
        court=court, pairs=[["eve", "frank"], ["grace", "heidi"]], created_by=eve
    )

    services.unsign_pair(active, pair_id=pair_for(active, "alice").id, requesting_user=bob)

    e1.refresh_from_db()
    e2.refresh_from_db()
    assert e1.status == QueueEntry.Status.ACTIVE
    assert e1.pairs.count() == 1
    assert e2.status == QueueEntry.Status.WAITING


# Row 28: malformed pairs payloads rejected
def test_malformed_pairs_payloads_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())

    with pytest.raises(services.ServiceError):
        services.create_queue_entry(court=court, pairs=[], created_by=alice)

    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court, pairs=[["alice", "bob", "carol"]], created_by=alice
        )

    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court, pairs=[["alice", "bob"], ["alice", "carol"]], created_by=alice
        )


# Row 29: per-court duplicate-signup check still applies to joins
def test_join_rejected_for_username_already_on_court():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    services.create_queue_entry(court=court, pairs=[["eve", "frank"]], created_by=eve)
    e = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    with pytest.raises(services.ServiceError):
        services.join_open_slot(e, usernames=["eve", "bob"], requesting_user=eve)


# Row 30: join_open_slot requires the requesting user to be one of the pair
def test_join_requires_requester_in_pair():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    make_user("eve", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())
    grace = make_user("grace", expires_at=future_expiry())

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    e = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    with pytest.raises(services.ServiceError):
        services.join_open_slot(e, usernames=["eve", "frank"], requesting_user=grace)
