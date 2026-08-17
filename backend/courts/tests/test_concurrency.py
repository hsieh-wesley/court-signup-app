import threading

import pytest
from django import db as django_db
from django.db import transaction

from courts import services
from courts.models import Court, Pair, QueueEntry
from courts.tests.factories import future_expiry, make_court, make_user

pytestmark = pytest.mark.django_db(transaction=True)


# Row 8: concurrent promotion attempts never produce two active entries.
def test_concurrent_promote_never_double_activates():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())

    for creator, players in [(alice, (alice, bob)), (carol, (carol, dave))]:
        entry = QueueEntry.objects.create(
            court=court, created_by=creator, status=QueueEntry.Status.WAITING
        )
        Pair.objects.create(
            entry=entry, slot=1, player_1=players[0], player_2=players[1], created_by=creator
        )

    errors = []

    def worker():
        django_db.connections.close_all()
        try:
            # Mirrors real call sites (reap/create/unsign), which always run
            # _promote_next_if_free inside an atomic block holding the
            # Court row lock.
            with transaction.atomic():
                locked_court = Court.objects.select_for_update().get(pk=court.pk)
                services._promote_next_if_free(locked_court)
        except Exception as exc:  # pragma: no cover - surfaced via errors list
            errors.append(exc)
        finally:
            django_db.connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    active_count = QueueEntry.objects.filter(
        court=court, status=QueueEntry.Status.ACTIVE
    ).count()
    assert active_count == 1


# Row 35: concurrent joins to the same open slot on the same entry — only one pair wins.
def test_concurrent_join_never_double_fills_a_slot():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())

    # Keep the court occupied so the target entry E stays WAITING throughout.
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    candidates = []
    for i in range(8):
        p1 = make_user(f"p{i}a", expires_at=future_expiry())
        p2 = make_user(f"p{i}b", expires_at=future_expiry())
        candidates.append((p1, p2))

    errors = []
    successes = []

    def worker(p1, p2):
        django_db.connections.close_all()
        try:
            services.join_open_slot(
                entry, usernames=[p1.username, p2.username], requesting_user=p1
            )
            successes.append(p1.username)
        except services.ServiceError as exc:
            errors.append(exc)
        finally:
            django_db.connections.close_all()

    threads = [threading.Thread(target=worker, args=pair) for pair in candidates]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(errors) == 7
    entry.refresh_from_db()
    assert entry.pairs.count() == 2
