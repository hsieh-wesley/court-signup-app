import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from courts import activity_log, admin_services, services
from courts.models import CourtActivityLog, LoginLog
from courts.tests.factories import authed_client, make_admin_user, make_court, make_user

pytestmark = pytest.mark.django_db


def credential(username, password="pw12345"):
    return {"username": username, "password": password}


# DoD A: letters only, no digits/symbols
def test_validate_new_username_rejects_digits():
    with pytest.raises(services.ServiceError):
        services.validate_new_username("alice2")


def test_validate_new_username_rejects_too_long():
    with pytest.raises(services.ServiceError):
        services.validate_new_username("a" * 21)


def test_validate_new_username_accepts_plain_letters():
    services.validate_new_username("alice")  # does not raise


# DoD H: protected names, case-insensitive, only while membership is active
def test_protected_name_rejects_active_member_username_case_insensitive():
    admin_services.start_membership("alice", "5551230000")
    with pytest.raises(services.ServiceError, match="protected"):
        services.validate_new_username("ALICE")


def test_protected_name_check_excludes_self():
    _player, membership, _plaintext = admin_services.start_membership("alice", "5551230000")
    # Renaming the same account to the same name it already holds must not
    # be rejected as "colliding with itself".
    services.validate_new_username("alice", exclude_user_id=membership.player.user_id)


def test_expired_member_username_no_longer_specially_protected_but_still_taken():
    _player, membership, _plaintext = admin_services.start_membership(
        "alice", "5551230000", expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    # Ordinary uniqueness still blocks it -- expiration never frees a
    # username for someone else to grab.
    with pytest.raises(services.ServiceError, match="already taken"):
        services.validate_new_username("alice")


def test_admin_string_reserved():
    make_admin_user("admin")
    with pytest.raises(services.ServiceError, match="protected"):
        services.validate_new_username("admin")


# DoD A/I: starting a membership for a brand-new username creates the account
def test_start_membership_creates_new_account_with_initial_password():
    player, membership, plaintext = admin_services.start_membership("kate", "5551230099")
    assert player.user.username == "kate"
    assert plaintext is not None
    assert membership.phone_number == "5551230099"
    assert membership.expires_at is None


# DoD B/G: starting a membership for an EXISTING (non-member) player reuses
# that account -- never creates a duplicate.
def test_start_membership_reuses_existing_player_no_duplicate():
    alice = make_user("alice")  # pre-existing, non-member account
    player, membership, plaintext = admin_services.start_membership("alice", "5551230000")
    assert player.user_id == alice.id
    assert plaintext is None  # existing account keeps its existing password
    assert membership.player_id == player.id


def test_start_membership_rejects_phone_already_active_elsewhere():
    admin_services.start_membership("alice", "5551230000")
    with pytest.raises(services.ServiceError, match="already active"):
        admin_services.start_membership("bob", "5551230000")


def test_start_membership_rejects_second_concurrent_period():
    admin_services.start_membership("alice", "5551230000")
    with pytest.raises(services.ServiceError, match="already has an active membership"):
        admin_services.start_membership("alice", "5559990000")


def test_start_membership_rejects_bad_phone_format():
    with pytest.raises(services.ServiceError, match="10 digits"):
        admin_services.start_membership("alice", "12345")


# DoD G: renewal after a lapse reuses the same account/phone, no duplicate
def test_renewal_after_lapse_reuses_same_account_and_phone():
    player, first, _plaintext = admin_services.start_membership(
        "alice", "5551230000", expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    player2, second, plaintext2 = admin_services.start_membership("alice", "5551230000")
    assert player2.id == player.id
    assert plaintext2 is None  # existing account, not recreated
    assert second.id != first.id
    assert player.memberships.count() == 2


def test_update_membership_rejects_editing_a_lapsed_row():
    _player, membership, _plaintext = admin_services.start_membership(
        "alice", "5551230000", expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    with pytest.raises(services.ServiceError, match="ended"):
        admin_services.update_membership(membership, phone_number="5559998888")


def test_update_membership_edits_current_row_in_place():
    _player, membership, _plaintext = admin_services.start_membership("alice", "5551230000")
    admin_services.update_membership(membership, phone_number="5559998888")
    membership.refresh_from_db()
    assert membership.phone_number == "5559998888"


# DoD I/J/K: member check-in by phone
def test_member_check_in_returns_animal_only_password():
    court = make_court()
    admin_services.start_membership("kate", "5551230099")
    user, plaintext = services.member_check_in("5551230099", court.location)
    assert user.username == "kate"
    assert plaintext.isalpha()  # no digits
    log = LoginLog.objects.get(username="kate")
    assert log.context == LoginLog.Context.MEMBER_CHECK_IN
    assert log.membership_status == "member"


def test_member_check_in_regenerates_password_invalidating_the_old_one():
    court = make_court()
    admin_services.start_membership("kate", "5551230099")
    _user, first_password = services.member_check_in("5551230099", court.location)
    assert services.verify_credential("kate", first_password)  # works right after

    # Only 11 possible animal words, so redraw until we get a different one
    # from first_password (otherwise "old password no longer works" would
    # be trivially, coincidentally true even without real invalidation).
    second_password = first_password
    for _ in range(50):
        _user, second_password = services.member_check_in("5551230099", court.location)
        if second_password != first_password:
            break
    assert second_password != first_password

    with pytest.raises(services.ServiceError):
        services.verify_credential("kate", first_password)
    assert services.verify_credential("kate", second_password)


def test_member_check_in_rejects_unknown_phone():
    court = make_court()
    with pytest.raises(services.ServiceError, match="No member found"):
        services.member_check_in("5559999999", court.location)


def test_member_check_in_endpoint_no_password_required():
    court = make_court()
    admin_services.start_membership("kate", "5551230099")
    client = APIClient()
    resp = client.post(
        "/api/players/check-in/",
        {"phone_number": "5551230099", "location_id": court.location_id},
    )
    assert resp.status_code == 200
    assert resp.data["display_name"] == "kate"
    assert "token" not in resp.data


# DoD F: an expired membership blocks nothing -- the player keeps using
# their existing username+password like any non-member walk-in.
def test_expired_member_can_still_sign_up_as_a_walk_in():
    court = make_court()
    make_user("alice")  # pre-existing account, known password "pw12345"
    admin_services.start_membership(
        "alice", "5551230000", expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    make_user("bob")
    client = APIClient()
    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 201


def test_expired_member_phone_no_longer_found():
    court = make_court()
    admin_services.start_membership(
        "alice", "5551230000", expires_at=timezone.now() - datetime.timedelta(days=1)
    )
    with pytest.raises(services.ServiceError, match="No member found"):
        services.member_check_in("5551230000", court.location)


# History must reflect membership status AT THE TIME of the event, never
# retroactively reclassified by a later membership change.
def test_history_snapshot_reflects_status_at_event_time_not_current_status():
    court = make_court()
    alice = make_user("alice")  # non-member "January" activity
    bob = make_user("bob")
    client = APIClient()

    # "January": alice is not yet a member.
    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 201
    january_log = CourtActivityLog.objects.filter(event_type=CourtActivityLog.EventType.PAIR_ACTIVATED).latest("created_at")
    assert january_log.player_1_membership_status == "non_member"

    # Unsign so alice/bob are free to sign up again below.
    services.unsign_by_credentials([[credential("alice"), credential("bob")]])

    # "June": alice becomes a member.
    admin_services.start_membership("alice", "5551230000")

    resp = client.post(
        "/api/queue-entries/",
        {"court_id": court.id, "pairs": [[credential("alice"), credential("bob")]]},
        format="json",
    )
    assert resp.status_code == 201
    june_log = CourtActivityLog.objects.filter(event_type=CourtActivityLog.EventType.PAIR_ACTIVATED).latest("created_at")
    assert june_log.player_1_membership_status == "member"

    # The January row must remain non_member even though alice is now a
    # member -- never retroactively reclassified.
    january_log.refresh_from_db()
    assert january_log.player_1_membership_status == "non_member"


def test_admin_history_filters_by_membership_status():
    court = make_court()
    alice = make_user("alice")
    bob = make_user("bob")
    activity_log.log_player_auth_event(alice, court.location, LoginLog.Context.STATUS_CHECK)

    admin_services.start_membership("bob", "5551230000")
    activity_log.log_player_auth_event(bob, court.location, LoginLog.Context.MEMBER_CHECK_IN)

    admin = make_admin_user()
    client = authed_client(admin)

    member_rows = client.get("/api/admin/history/logins/?membership=member").data
    non_member_rows = client.get("/api/admin/history/logins/?membership=non_member").data

    assert any(r["username"] == "bob" for r in member_rows)
    assert not any(r["username"] == "alice" for r in member_rows)
    assert any(r["username"] == "alice" for r in non_member_rows)
    assert not any(r["username"] == "bob" for r in non_member_rows)


# Admin Membership tab surface
def test_admin_membership_list_shows_status_and_dates():
    admin_services.start_membership("kate", "5551230099")
    admin = make_admin_user()
    client = authed_client(admin)

    resp = client.get("/api/admin/memberships/")
    assert resp.status_code == 200
    row = next(r for r in resp.data if r["username"] == "kate")
    assert row["status"] == "active"
    assert row["phone_number"] == "5551230099"
    assert row["expires_at"] is None


def test_admin_membership_create_endpoint():
    admin = make_admin_user()
    client = authed_client(admin)
    resp = client.post("/api/admin/memberships/", {"username": "kate", "phone_number": "5551230099"})
    assert resp.status_code == 201
    assert resp.data["password"]  # shown once, new account


def test_admin_membership_patch_edits_current_period():
    admin_services.start_membership("kate", "5551230099")
    admin = make_admin_user()
    client = authed_client(admin)
    from courts.models import Player

    player = Player.objects.get(user__username="kate")
    resp = client.patch(f"/api/admin/memberships/{player.id}/", {"phone_number": "5559998888"})
    assert resp.status_code == 200
    assert resp.data["phone_number"] == "5559998888"
