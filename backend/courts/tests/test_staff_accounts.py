import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from courts import admin_services, services
from courts.models import Location, PlayerSession
from courts.tests.factories import authed_client, make_admin_user, make_user

User = get_user_model()

pytestmark = pytest.mark.django_db


# DoD E/F: staff can manage existing facilities/court counts but cannot
# create a brand-new one; admin can.
def test_staff_cannot_create_location():
    staff = make_admin_user("staff", is_superuser=False)
    client = authed_client(staff)
    resp = client.post("/api/admin/locations/", {"name": "New Place", "court_count": 3})
    assert resp.status_code == 403


def test_admin_can_create_location():
    admin = make_admin_user("admin")
    client = authed_client(admin)
    resp = client.post("/api/admin/locations/", {"name": "New Place", "court_count": 3})
    assert resp.status_code == 201


def test_staff_can_edit_existing_location_and_court_count():
    admin_services.create_location("Existing Place", court_count=2)
    location = Location.objects.get(name="Existing Place")
    staff = make_admin_user("staff", is_superuser=False)
    client = authed_client(staff)

    resp = client.patch(f"/api/admin/locations/{location.id}/", {"name": "Renamed Place"})
    assert resp.status_code == 200

    resp = client.post(f"/api/admin/locations/{location.id}/court-count/", {"count": 4})
    assert resp.status_code == 200


# Delete Location is admin/superuser-only, same as create.
def test_staff_cannot_delete_location():
    admin_services.create_location("No Delete For Staff", court_count=1)
    location = Location.objects.get(name="No Delete For Staff")
    staff = make_admin_user("staff", is_superuser=False)
    client = authed_client(staff)

    resp = client.post(f"/api/admin/locations/{location.id}/delete/")
    assert resp.status_code == 403
    assert Location.objects.filter(id=location.id).exists()


def test_admin_can_delete_location_with_no_history():
    admin_services.create_location("Delete Me", court_count=1)
    location = Location.objects.get(name="Delete Me")
    admin = make_admin_user("admin")
    client = authed_client(admin)

    resp = client.post(f"/api/admin/locations/{location.id}/delete/")
    assert resp.status_code == 204
    assert not Location.objects.filter(id=location.id).exists()


def test_admin_delete_location_with_history_returns_409_and_explanation():
    location = admin_services.create_location("History Blocked Delete", court_count=1)
    court = location.courts.get(number=1)
    alice = make_user("alice")
    make_user("bob")
    services.create_queue_entry(court=court, pairs=[["alice", "bob"]], created_by=alice)
    admin = make_admin_user("admin")
    client = authed_client(admin)

    resp = client.post(f"/api/admin/locations/{location.id}/delete/")
    assert resp.status_code == 409
    assert "history" in resp.json()["detail"].lower()
    assert Location.objects.filter(id=location.id).exists()


# DoD F2/F3: only admin can reset staff's password; staff cannot reset it
# (its own or anyone else's), and the reset invalidates existing sessions.
def test_admin_can_reset_staff_password():
    call_command("seed_staff_account")
    admin = make_admin_user("admin")
    client = authed_client(admin)

    resp = client.post("/api/admin/staff/reset-password/")
    assert resp.status_code == 200
    new_password = resp.data["password"]
    assert new_password != "staffpass123"

    assert services.verify_credential("staff", new_password)
    with pytest.raises(services.ServiceError):
        services.verify_credential("staff", "staffpass123")


def test_staff_cannot_reset_its_own_password():
    call_command("seed_staff_account")
    staff = User.objects.get(username="staff")
    client = authed_client(staff)
    resp = client.post("/api/admin/staff/reset-password/")
    assert resp.status_code == 403


def test_reset_staff_password_invalidates_existing_sessions():
    call_command("seed_staff_account")
    staff = User.objects.get(username="staff")
    PlayerSession.objects.create(user=staff)
    assert PlayerSession.objects.filter(user=staff).exists()

    admin_services.reset_staff_password()
    assert not PlayerSession.objects.filter(user=staff).exists()


# DoD F4: re-running the seed command never reverts an admin's password change.
def test_seed_staff_account_does_not_reset_existing_password():
    call_command("seed_staff_account")
    admin_services.reset_staff_password()
    staff = User.objects.get(username="staff")
    changed_hash = staff.password

    call_command("seed_staff_account")
    staff.refresh_from_db()
    assert staff.password == changed_hash


def test_seed_staff_account_creates_with_default_password():
    call_command("seed_staff_account")
    user = services.verify_credential("staff", "staffpass123")
    assert user.is_staff
    assert not user.is_superuser


# The staff account's current password is viewable by staff (their own
# account) and admin, without needing a reset -- unlike the reset action
# itself, which stays admin/superuser-only.
def test_seed_staff_account_makes_password_immediately_viewable():
    call_command("seed_staff_account")
    staff = User.objects.get(username="staff")
    client = authed_client(staff)

    resp = client.get("/api/admin/staff/credential/")
    assert resp.status_code == 200
    assert resp.data["password"] == "staffpass123"


def test_reset_staff_password_updates_the_viewable_password():
    call_command("seed_staff_account")
    new_password = admin_services.reset_staff_password()
    staff = User.objects.get(username="staff")
    client = authed_client(staff)

    resp = client.get("/api/admin/staff/credential/")
    assert resp.status_code == 200
    assert resp.data["password"] == new_password


def test_admin_can_also_view_staff_password():
    call_command("seed_staff_account")
    admin = make_admin_user("admin")
    client = authed_client(admin)

    resp = client.get("/api/admin/staff/credential/")
    assert resp.status_code == 200
    assert resp.data["password"] == "staffpass123"


def test_unauthenticated_cannot_view_staff_password():
    from rest_framework.test import APIClient

    client = APIClient()
    resp = client.get("/api/admin/staff/credential/")
    assert resp.status_code in (401, 403)


def test_staff_credential_reports_null_before_any_password_is_set():
    # An account that was never created through seed_staff_account/
    # reset_staff_password (so StaffCredential was never synced).
    User.objects.create_user(username="staff", password="whatever", is_staff=True)
    admin = make_admin_user("admin")
    client = authed_client(admin)

    resp = client.get("/api/admin/staff/credential/")
    assert resp.status_code == 200
    assert resp.data["password"] is None
