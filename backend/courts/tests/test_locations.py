import pytest

from courts import activity_log, admin_services, services
from courts.models import Court, CourtActivityLog, Location, LoginLog, QueueEntry
from courts.tests.factories import make_court, make_location, make_user

pytestmark = pytest.mark.django_db


# Row 1: default court creation
def test_create_location_defaults_to_ten_courts():
    location = admin_services.create_location("Test Location 2")
    assert location.courts.count() == 10
    assert sorted(location.courts.values_list("number", flat=True)) == list(range(1, 11))


def test_create_location_with_custom_count():
    location = admin_services.create_location("UCLA", court_count=6)
    assert location.courts.count() == 6
    assert sorted(location.courts.values_list("number", flat=True)) == list(range(1, 7))


def test_create_location_rejects_count_over_100():
    with pytest.raises(services.ServiceError):
        admin_services.create_location("Too Big", court_count=101)


def test_create_location_rejects_duplicate_name():
    make_location("Sunnyvale Badminton Center")
    with pytest.raises(services.ServiceError):
        admin_services.create_location("Sunnyvale Badminton Center")


# Row 4: same court number at different locations never conflicts
def test_same_court_number_at_different_locations_no_conflict():
    loc_a = make_location("Location A")
    loc_b = make_location("Location B")
    court_a = admin_services.create_court(loc_a, number=1)
    court_b = admin_services.create_court(loc_b, number=1)
    assert court_a.id != court_b.id
    assert court_a.number == court_b.number == 1


# Row 2/5: reducing court count deactivates occupied courts safely
def test_reducing_court_count_drops_occupants_and_deactivates_above_target():
    location = admin_services.create_location("Drop Test", court_count=10)
    court8 = Court.objects.get(location=location, number=8)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court8, pairs=[["alice", "bob"]], created_by=alice)

    admin_services.set_court_count(location, 6)

    entry.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED
    for n in range(7, 11):
        assert not Court.objects.get(location=location, number=n).is_active
    for n in range(1, 7):
        assert Court.objects.get(location=location, number=n).is_active


def test_reducing_court_count_rejects_out_of_range():
    location = admin_services.create_location("Range Test")
    with pytest.raises(services.ServiceError):
        admin_services.set_court_count(location, 0)
    with pytest.raises(services.ServiceError):
        admin_services.set_court_count(location, 101)


# Row 3/6: increasing court count reactivates existing rows, never duplicates
def test_increasing_court_count_reactivates_not_recreates():
    location = admin_services.create_location("Reactivate Test", court_count=10)
    admin_services.set_court_count(location, 6)
    court7_before = Court.objects.get(location=location, number=7)
    assert not court7_before.is_active

    admin_services.set_court_count(location, 9)

    court7_after = Court.objects.get(location=location, number=7)
    assert court7_after.id == court7_before.id
    assert court7_after.is_active is True
    assert Court.objects.filter(location=location).count() == 10  # no duplicates, court 10 stays inactive
    assert not Court.objects.get(location=location, number=10).is_active


def test_increasing_court_count_logs_reactivation():
    location = admin_services.create_location("Reactivate Log Test", court_count=10)
    admin_services.set_court_count(location, 6)
    CourtActivityLog.objects.all().delete()

    admin_services.set_court_count(location, 8)

    reactivated = CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.COURT_REACTIVATED
    )
    assert reactivated.count() == 2
    assert set(reactivated.values_list("court_number", flat=True)) == {7, 8}


# Location-level deactivation
def test_deactivate_location_drops_occupants_first():
    location = admin_services.create_location("Deactivate Loc Test", court_count=2)
    court = Court.objects.get(location=location, number=1)
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin_services.edit_location(location, is_active=False)

    entry.refresh_from_db()
    location.refresh_from_db()
    assert entry.status == QueueEntry.Status.COMPLETED
    assert location.is_active is False


def test_deactivated_location_blocks_new_signups_even_if_court_still_active():
    location = admin_services.create_location("Blocked Loc Test", court_count=1)
    court = Court.objects.get(location=location, number=1)
    admin_services.edit_location(location, is_active=False)
    court.refresh_from_db()
    assert court.is_active is True  # individual court untouched

    alice = make_user("alice")
    make_user("bob")
    with pytest.raises(services.ServiceError):
        services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)


def test_create_court_helper_auto_numbers():
    court1 = make_court()
    court2 = make_court()
    assert court2.number == court1.number + 1
    assert court1.location_id == court2.location_id


# Delete Location: hard-delete only when zero history, otherwise refuse.
def test_delete_location_with_no_history_hard_deletes_it_and_its_courts():
    location = admin_services.create_location("Fresh Location", court_count=3)
    location_id = location.id

    admin_services.delete_location(location)

    assert not Location.objects.filter(id=location_id).exists()
    assert not Court.objects.filter(location_id=location_id).exists()


def test_delete_location_refuses_when_queue_history_exists():
    location = admin_services.create_location("Queue History Loc", court_count=1)
    court = Court.objects.get(location=location, number=1)
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    with pytest.raises(services.ServiceError):
        admin_services.delete_location(location)

    assert Location.objects.filter(id=location.id).exists()


def test_delete_location_refuses_when_activity_log_history_exists():
    location = admin_services.create_location("Activity History Loc", court_count=1)
    court = Court.objects.get(location=location, number=1)
    activity_log.log_court_event(CourtActivityLog.EventType.COURT_DEACTIVATED, court)
    assert CourtActivityLog.objects.filter(location=location).exists()

    with pytest.raises(services.ServiceError):
        admin_services.delete_location(location)


def test_delete_location_refuses_when_login_log_history_exists():
    location = admin_services.create_location("Login History Loc", court_count=1)
    alice = make_user("alice")
    LoginLog.objects.create(
        user=alice, username="alice", location=location, context=LoginLog.Context.CHECK_IN
    )

    with pytest.raises(services.ServiceError):
        admin_services.delete_location(location)


def test_has_history_reflects_delete_eligibility():
    empty_location = admin_services.create_location("Empty History Loc", court_count=1)
    assert admin_services.location_has_history(empty_location) is False

    court = Court.objects.get(location=empty_location, number=1)
    activity_log.log_court_event(CourtActivityLog.EventType.COURT_DEACTIVATED, court)
    assert admin_services.location_has_history(empty_location) is True
