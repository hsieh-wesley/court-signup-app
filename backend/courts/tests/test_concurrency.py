import threading

import pytest
from django import db as django_db
from django.db import transaction

from courts import services
from courts.models import Court, QueueEntry
from courts.tests.factories import future_expiry, make_court, make_user

pytestmark = pytest.mark.django_db(transaction=True)


# Row 8: concurrent promotion attempts never produce two active entries.
def test_concurrent_promote_never_double_activates():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    bob = make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    dave = make_user("dave", expires_at=future_expiry())

    for creator, pair in [(alice, [alice, bob]), (carol, [carol, dave])]:
        entry = QueueEntry.objects.create(
            court=court, created_by=creator, status=QueueEntry.Status.WAITING
        )
        entry.members.set(pair)

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
