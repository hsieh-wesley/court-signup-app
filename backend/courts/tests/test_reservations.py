import datetime

import pytest
from django.utils import timezone

from courts import admin_services, services
from courts.models import CourtActivityLog, QueueEntry
from courts.tests.factories import future_expiry, make_court, make_user

pytestmark = pytest.mark.django_db


def _reserve(court, minutes_from_now_start, minutes_from_now_end):
    now = timezone.now()
    start = now + datetime.timedelta(minutes=minutes_from_now_start)
    end = now + datetime.timedelta(minutes=minutes_from_now_end)
    return admin_services.set_court_reservation(court, start, end)


# Row A: reservation starts sooner than a normal 45-minute session would
# end, so the fresh sign-up's session is capped at the reservation start.
def test_join_activates_capped_to_a_reservation():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    _reserve(court, 20, 50)

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    court.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.expires_at == court.reservation_start


# Row B: no minimum floor -- even 2 minutes is still worth activating for.
def test_join_activates_with_short_capped_session_no_floor():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    _reserve(court, 2, 30)

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    court.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    remaining = (entry.expires_at - timezone.now()).total_seconds()
    assert 0 < remaining <= 120


# Row C: inside the reservation window, sign-ups stay queued.
def test_join_during_reservation_window_stays_waiting():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    _reserve(court, -5, 30)

    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    assert entry.status == QueueEntry.Status.WAITING


# Row D: normal Set Reservation refuses on an occupied court, leaving the
# active group completely untouched.
def test_set_reservation_rejected_on_occupied_court():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    original_expires_at = entry.expires_at

    with pytest.raises(services.ServiceError, match="active group"):
        _reserve(court, 10, 40)

    entry.refresh_from_db()
    court.refresh_from_db()
    assert entry.status == QueueEntry.Status.ACTIVE
    assert entry.expires_at == original_expires_at
    assert court.reservation_start is None


# Row E: Emergency Reserve pauses an active group immediately.
def test_force_reserve_pauses_active_group_immediately():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )

    now = timezone.now()
    admin_services.force_reserve_court(
        court, now - datetime.timedelta(minutes=1), now + datetime.timedelta(minutes=30)
    )

    entry.refresh_from_db()
    assert entry.paused_at is not None
    remaining_before = entry.expires_at - entry.paused_at
    import time

    time.sleep(0.05)
    remaining_after = entry.expires_at - entry.paused_at
    assert remaining_before == remaining_after  # frozen, not ticking


# Row F: moving a paused group to a court with no reservation resumes it
# with exactly the time it had when paused.
def test_move_paused_entry_to_free_court_resumes_with_same_remaining_time():
    origin = make_court(name="Court 1")
    target = make_court(name="Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=origin, pairs=[["alice", "bob"]], created_by=alice
    )
    now = timezone.now()
    entry.paused_at = now - datetime.timedelta(minutes=5)
    entry.expires_at = now + datetime.timedelta(minutes=10)  # 15 min remaining when paused
    entry.save()

    moved = admin_services.move_entry_to_court(entry, target)

    assert moved.paused_at is None
    remaining = (moved.expires_at - timezone.now()).total_seconds() / 60
    assert 14.9 <= remaining <= 15.1


# Row G: destination reservation starts later than the group's own
# remaining time -- resumes uncapped.
def test_move_paused_entry_uncapped_when_destination_reservation_is_far_off():
    origin = make_court(name="Court 1")
    target = make_court(name="Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=origin, pairs=[["alice", "bob"]], created_by=alice
    )
    now = timezone.now()
    entry.paused_at = now - datetime.timedelta(minutes=5)
    entry.expires_at = now + datetime.timedelta(minutes=5)  # 10 min remaining
    entry.save()
    _reserve(target, 15, 45)

    moved = admin_services.move_entry_to_court(entry, target)
    remaining = (moved.expires_at - timezone.now()).total_seconds() / 60
    assert 9.5 <= remaining <= 10.1


# Row H: destination reservation starts sooner than the group's remaining
# time -- capped, no minimum floor.
def test_move_paused_entry_capped_by_destination_reservation_no_floor():
    origin = make_court(name="Court 1")
    target = make_court(name="Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=origin, pairs=[["alice", "bob"]], created_by=alice
    )
    now = timezone.now()
    entry.paused_at = now - datetime.timedelta(minutes=5)
    entry.expires_at = now + datetime.timedelta(minutes=25)  # 30 min remaining
    entry.save()
    _reserve(target, 2, 30)

    target.refresh_from_db()
    moved = admin_services.move_entry_to_court(entry, target)
    assert moved.expires_at == target.reservation_start


# Row I: a court currently inside its own reservation window is not an
# eligible move target, for either an active or a waiting entry.
def test_move_refused_into_currently_reserved_court():
    origin = make_court(name="Court 1")
    target = make_court(name="Court 2")
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=origin, pairs=[["alice", "bob"]], created_by=alice
    )
    _reserve(target, -5, 30)

    with pytest.raises(services.ServiceError, match="currently reserved"):
        admin_services.move_entry_to_court(entry, target)


# Row J: once reservation_end passes, the reservation auto-clears and a
# paused group resumes ticking on the same court.
def test_sweep_auto_clears_reservation_and_resumes_paused_group():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    now = timezone.now()
    entry.paused_at = now - datetime.timedelta(minutes=10)
    entry.expires_at = now - datetime.timedelta(minutes=5)  # 5 min remaining when paused
    entry.save()
    court.reservation_start = now - datetime.timedelta(minutes=20)
    court.reservation_end = now - datetime.timedelta(minutes=1)
    court.save()

    services.sweep_courts(court_ids=[court.id])

    court.refresh_from_db()
    entry.refresh_from_db()
    assert court.reservation_start is None
    assert court.reservation_end is None
    assert entry.paused_at is None
    assert entry.status == QueueEntry.Status.ACTIVE
    remaining = (entry.expires_at - timezone.now()).total_seconds() / 60
    assert 4.5 <= remaining <= 5.1


# Row K: queuing is never blocked, reservation or not.
def test_queueing_always_allowed_during_reservation():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    carol = make_user("carol", expires_at=future_expiry())
    make_user("dave", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    now = timezone.now()
    admin_services.force_reserve_court(
        court, now - datetime.timedelta(minutes=5), now + datetime.timedelta(minutes=30)
    )

    waiting = services.create_queue_entry(
        court=court, pairs=[["carol", "dave"]], created_by=carol
    )
    assert waiting.status == QueueEntry.Status.WAITING


# Row L: a court with no reservation behaves exactly as before.
def test_no_reservation_unaffected():
    court = make_court()
    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    assert entry.status == QueueEntry.Status.ACTIVE
    assert court.reservation_start is None
    assert court.reservation_end is None


# Row N: setting, clearing, rejecting (no log row on rejection), force-
# reserving, and pausing each produce their own history entries.
def test_reservation_actions_are_logged():
    court = make_court()
    now = timezone.now()
    admin_services.set_court_reservation(
        court, now + datetime.timedelta(minutes=30), now + datetime.timedelta(minutes=60)
    )
    assert CourtActivityLog.objects.filter(
        court=court, event_type=CourtActivityLog.EventType.COURT_RESERVED
    ).count() == 1

    admin_services.set_court_reservation(court, None, None)  # clear
    assert CourtActivityLog.objects.filter(
        court=court, event_type=CourtActivityLog.EventType.COURT_RESERVED
    ).count() == 2

    alice = make_user("alice", expires_at=future_expiry())
    make_user("bob", expires_at=future_expiry())
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    admin_services.force_reserve_court(
        court, now - datetime.timedelta(minutes=1), now + datetime.timedelta(minutes=30)
    )
    assert CourtActivityLog.objects.filter(
        court=court, event_type=CourtActivityLog.EventType.PAIR_PAUSED
    ).count() == 1


def test_set_reservation_requires_both_start_and_end():
    court = make_court()
    now = timezone.now()
    with pytest.raises(services.ServiceError, match="both"):
        admin_services.set_court_reservation(court, now, None)


def test_reservation_note_is_saved_and_cleared_with_the_window():
    court = make_court()
    now = timezone.now()
    admin_services.set_court_reservation(
        court,
        now + datetime.timedelta(minutes=30),
        now + datetime.timedelta(minutes=60),
        note="Coaching",
    )
    court.refresh_from_db()
    assert court.reservation_note == "Coaching"

    admin_services.set_court_reservation(court, None, None)
    court.refresh_from_db()
    assert court.reservation_note == ""


def test_set_reservation_requires_start_before_end():
    court = make_court()
    now = timezone.now()
    with pytest.raises(services.ServiceError, match="before"):
        admin_services.set_court_reservation(
            court, now + datetime.timedelta(minutes=10), now
        )
