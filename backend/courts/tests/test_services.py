import datetime

import pytest
from django.utils import timezone

from courts import services
from courts.models import QueueEntry
from courts.tests.factories import future_expiry, make_court, make_user

pytestmark = pytest.mark.django_db


# Row 1/2: group size must be 2 or 4
def test_join_with_one_person_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(court=court, usernames=["alice"], created_by=alice)


def test_join_with_three_people_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court, usernames=["alice", "bob", "carol"], created_by=alice
        )


# Row 3: join with 2 on an empty court activates immediately
def test_join_pair_on_empty_court_activates_immediately():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, usernames=["alice", "bob"], created_by=alice
    )
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.expires_at is not None


# Row 4/5: per-court uniqueness, not global
def test_duplicate_username_rejected_on_same_court():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())
    services.create_queue_entry(court=court, usernames=["alice", "bob"], created_by=alice)
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(
            court=court, usernames=["alice", "dave"], created_by=alice
        )


def test_same_username_allowed_on_different_court():
    court1 = make_court("Court 1")
    court2 = make_court("Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    services.create_queue_entry(court=court1, usernames=["alice", "bob"], created_by=alice)
    entry2 = services.create_queue_entry(
        court=court2, usernames=["alice", "eve"], created_by=alice
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
    services.create_queue_entry(court=court, usernames=["alice", "bob"], created_by=alice)
    e1 = services.create_queue_entry(court=court, usernames=["carol", "dave"], created_by=carol)
    e2 = services.create_queue_entry(court=court, usernames=["eve", "frank"], created_by=eve)
    assert e1.status == QueueEntry.Status.WAITING
    assert e2.status == QueueEntry.Status.WAITING

    services.unsign(
        QueueEntry.objects.get(court=court, status=QueueEntry.Status.ACTIVE),
        usernames=["alice", "bob"],
        requesting_user=alice,
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

    active = services.create_queue_entry(court=court, usernames=["alice", "bob"], created_by=alice)
    waiting = services.create_queue_entry(court=court, usernames=["carol", "dave"], created_by=carol)

    active.expires_at = timezone.now() - datetime.timedelta(minutes=5)
    active.save()

    services.reap_expired_reservations(court_ids=[court.id])

    active.refresh_from_db()
    waiting.refresh_from_db()
    assert active.status == QueueEntry.Status.EXPIRED
    assert waiting.status == QueueEntry.Status.ACTIVE
    assert waiting.expires_at > timezone.now()


# Row 9/10: unsign in pairs, 4 -> 2 stays active, 2 -> 0 ends + promotes
def test_unsign_two_of_four_leaves_two_active():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())

    entry = services.create_queue_entry(
        court=court, usernames=["alice", "bob", "carol", "dave"], created_by=alice
    )
    original_expiry = entry.expires_at

    updated = services.unsign(entry, usernames=["alice", "bob"], requesting_user=bob)
    assert updated.status == QueueEntry.Status.ACTIVE
    assert updated.expires_at == original_expiry
    assert set(updated.members.values_list("username", flat=True)) == {"carol", "dave"}


def test_unsign_remaining_two_ends_entry_and_promotes_next():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())
    eve = make_user("eve", expires_at=future_expiry())
    frank = make_user("frank", expires_at=future_expiry())

    entry = services.create_queue_entry(
        court=court, usernames=["alice", "bob", "carol", "dave"], created_by=alice
    )
    waiting = services.create_queue_entry(court=court, usernames=["eve", "frank"], created_by=eve)

    services.unsign(entry, usernames=["alice", "bob"], requesting_user=bob)
    entry.refresh_from_db()
    ended = services.unsign(entry, usernames=["carol", "dave"], requesting_user=carol)

    assert ended.status == QueueEntry.Status.COMPLETED
    waiting.refresh_from_db()
    assert waiting.status == QueueEntry.Status.ACTIVE


# Row 11/12: odd removal rejected
def test_unsign_single_player_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(court=court, usernames=["alice", "bob"], created_by=alice)
    with pytest.raises(services.ServiceError):
        services.unsign(entry, usernames=["alice"], requesting_user=alice)


def test_unsign_three_of_four_rejected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, usernames=["alice", "bob", "carol", "dave"], created_by=alice
    )
    with pytest.raises(services.ServiceError):
        services.unsign(entry, usernames=["alice", "bob", "carol"], requesting_user=alice)


# Row 15: resign after full unsign
def test_resign_after_full_unsign():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    make_user("frank", expires_at=future_expiry())

    entry = services.create_queue_entry(court=court, usernames=["alice", "bob"], created_by=alice)
    services.unsign(entry, usernames=["alice", "bob"], requesting_user=alice)

    new_entry = services.create_queue_entry(
        court=court, usernames=["alice", "frank"], created_by=alice
    )
    assert new_entry.status == QueueEntry.Status.ACTIVE
