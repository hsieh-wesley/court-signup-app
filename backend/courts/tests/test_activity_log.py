import datetime

import pytest
from django.utils import timezone

from courts import activity_log, admin_services, services
from courts.models import CourtActivityLog, LoginLog
from courts.tests.factories import make_admin_user, make_court, make_user, pair_for

pytestmark = pytest.mark.django_db


# Row 13: created straight onto an empty court -> only PAIR_ACTIVATED, never also PAIR_QUEUED
def test_pair_created_on_empty_court_logs_only_activated():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ACTIVATED
    ).count() == 1
    assert not CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_QUEUED
    ).exists()


# Row 14: queued then later promoted -> two distinct events
def test_pair_queued_then_promoted_logs_both_events():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")

    active_entry = services.create_queue_entry(
        court=court, pairs=[["alice", "bob"]], created_by=alice
    )
    services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)

    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_QUEUED,
        player_1_username="carol",
    ).count() == 1

    services.unsign_pair(
        active_entry, pair_id=pair_for(active_entry, "alice").id, requesting_user=alice
    )

    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ACTIVATED,
        player_1_username="carol",
    ).count() == 1


def test_open_slot_join_logged():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    carol = make_user("carol")
    make_user("dave")
    eve = make_user("eve")
    make_user("frank")

    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry = services.create_queue_entry(court=court, pairs=[["carol", "dave"]], created_by=carol)
    services.join_open_slot(entry, usernames=["eve", "frank"], requesting_user=eve)

    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.OPEN_SLOT_JOINED,
        player_1_username="eve",
    ).count() == 1


def test_unsign_logs_pair_ended_with_reason():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    services.unsign_pair(entry, pair_id=pair_for(entry, "alice").id, requesting_user=alice)

    log = CourtActivityLog.objects.get(event_type=CourtActivityLog.EventType.PAIR_ENDED)
    assert log.reason == CourtActivityLog.Reason.UNSIGNED
    assert log.actor_username == ""


def test_admin_remove_logs_pair_ended_with_actor():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    admin = make_user("staffer")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin_services.remove_player_from_court(court, "alice", actor=admin)

    log = CourtActivityLog.objects.get(event_type=CourtActivityLog.EventType.PAIR_ENDED)
    assert log.reason == CourtActivityLog.Reason.ADMIN_REMOVED
    assert log.actor_username == "staffer"


def test_expired_reservation_logs_pair_ended_with_expired_reason():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    entry = services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    entry.expires_at = timezone.now() - datetime.timedelta(minutes=1)
    entry.save()

    services.reap_expired_reservations(court_ids=[court.id])

    log = CourtActivityLog.objects.get(event_type=CourtActivityLog.EventType.PAIR_ENDED)
    assert log.reason == CourtActivityLog.Reason.EXPIRED


# Row 15/16: drop_court logs one PAIR_ENDED per pair plus exactly one COURT_DROPPED,
# and the COURT_DROPPED row still appears even for an empty court.
def test_drop_court_logs_per_pair_and_one_court_event():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    admin_services.drop_court(court)

    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ENDED,
        reason=CourtActivityLog.Reason.COURT_DROPPED,
    ).count() == 1
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.COURT_DROPPED
    ).count() == 1


def test_drop_empty_court_still_logs_court_dropped():
    court = make_court()
    admin_services.drop_court(court)
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.COURT_DROPPED
    ).count() == 1
    assert not CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ENDED
    ).exists()


def test_deactivate_court_logs_deactivated_event():
    court = make_court()
    admin_services.deactivate_court(court)
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.COURT_DEACTIVATED
    ).count() == 1


# Row 17: snapshot fields survive a later rename
def test_location_rename_does_not_corrupt_old_log_snapshot():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    original_name = court.location.name

    admin_services.edit_location(court.location, name="Renamed Facility")

    log = CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ACTIVATED
    ).get()
    assert log.location_name == original_name
    assert log.location_name != "Renamed Facility"


def test_status_check_never_logs_password():
    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)

    user = services.verify_credential("alice", "pw12345")
    activity_log.log_player_auth_event(user, court.location, LoginLog.Context.STATUS_CHECK)

    log = LoginLog.objects.get(user=alice)
    assert log.context == LoginLog.Context.STATUS_CHECK
    assert "pw12345" not in vars(log).values()


def test_admin_login_never_logs_password_or_token_string():
    admin = make_admin_user()
    court = make_court()
    session = services.create_player_session(admin, court.location)
    # The log row has no field capable of holding a password/token at all —
    # confirm the session key itself never appears anywhere in the log table.
    log = LoginLog.objects.get(user=admin, context=LoginLog.Context.ADMIN_LOGIN)
    assert session.key not in vars(log).values()


# Row 8: registration writes a REGISTRATION LoginLog row, no PlayerSession
def test_registration_logs_context_with_facility_no_session():
    from rest_framework.test import APIClient

    from courts.models import PlayerSession

    court = make_court()
    client = APIClient()
    resp = client.post(
        "/api/players/register/",
        {"username": "newplayer", "location_id": court.location_id},
    )
    assert resp.status_code == 201
    assert "token" not in resp.data

    log = LoginLog.objects.get(username="newplayer")
    assert log.context == LoginLog.Context.REGISTRATION
    assert log.location_id == court.location_id
    assert PlayerSession.objects.count() == 0


# Row 10: a successful court join does not create a redundant LoginLog row —
# CourtActivityLog already fully represents it.
def test_successful_join_creates_no_login_log_rows():
    from rest_framework.test import APIClient

    court = make_court()
    make_user("alice")
    make_user("bob")

    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {
            "court_id": court.id,
            "pairs": [[
                {"username": "alice", "password": "pw12345"},
                {"username": "bob", "password": "pw12345"},
            ]],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert LoginLog.objects.count() == 0
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ACTIVATED
    ).count() == 1
