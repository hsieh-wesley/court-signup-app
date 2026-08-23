import datetime

import pytest
from django.utils import timezone

from courts import activity_log, admin_services, password_gen, services
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

    services.sweep_courts(court_ids=[court.id])

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


# Row 10: a successful court join is fully represented by CourtActivityLog,
# but it also stamps each player's same-day facility presence (DoD K) —
# one CHECK_IN LoginLog row per player, so neither needs a separate Check In
# tap to show up as Waiting Room after they leave the court.
def test_successful_join_stamps_one_check_in_per_player():
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
    assert LoginLog.objects.count() == 2
    assert set(LoginLog.objects.values_list("username", flat=True)) == {"alice", "bob"}
    assert all(log.context == LoginLog.Context.CHECK_IN for log in LoginLog.objects.all())
    assert all(log.location_id == court.location_id for log in LoginLog.objects.all())
    assert CourtActivityLog.objects.filter(
        event_type=CourtActivityLog.EventType.PAIR_ACTIVATED
    ).count() == 1


# DoD L: a player who already checked in today doesn't get a duplicate row
# just for signing up for a court afterward.
def test_join_does_not_duplicate_an_existing_check_in_today():
    from rest_framework.test import APIClient

    court = make_court()
    alice = make_user("alice")
    make_user("bob")
    # Simulate a pre-existing same-day presence stamp (e.g. from an earlier
    # court action) — explicit username/password Check In no longer exists.
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.CHECK_IN)
    assert LoginLog.objects.filter(username="alice").count() == 1

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
    assert LoginLog.objects.filter(username="alice").count() == 1
    assert LoginLog.objects.filter(username="bob").count() == 1


# DoD I: the phone-based member Check In endpoint stamps presence with no
# session/token, and returns a fresh animal-only password.
def test_member_check_in_endpoint_stamps_presence_with_no_session():
    from rest_framework.test import APIClient

    court = make_court()
    admin_services.start_membership("alice", "5551230000")

    client = APIClient()
    resp = client.post(
        "/api/players/check-in/",
        {"phone_number": "5551230000", "location_id": court.location_id},
    )
    assert resp.status_code == 200
    assert "token" not in resp.data
    assert resp.data["password"] in password_gen.MEMBER_ANIMALS
    log = LoginLog.objects.get(username="alice")
    assert log.context == LoginLog.Context.MEMBER_CHECK_IN
    assert log.membership_status == "member"
    assert log.location_id == court.location_id
