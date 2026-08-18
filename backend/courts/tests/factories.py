from django.contrib.auth import get_user_model
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework.test import APIClient

from courts.models import Court, Location, Player, PlayerSession

User = get_user_model()

_DEFAULT_LOCATION_NAME = "Test Location"


def make_user(username, expires_at=None):
    user = User.objects.create_user(username=username, password="pw12345")
    kwargs = {"user": user, "display_name": username}
    if expires_at is not None:
        kwargs["expires_at"] = expires_at
    Player.objects.create(**kwargs)
    return user


def make_admin_user(username="admin"):
    """A staff user with no Player record — admins aren't necessarily players."""
    return User.objects.create_user(username=username, password="pw12345", is_staff=True)


def default_location():
    """The shared implicit location used by make_court()/authed_client()
    when no location is given, so they stay consistent with each other
    without every existing test needing to pass one explicitly."""
    location, _ = Location.objects.get_or_create(name=_DEFAULT_LOCATION_NAME)
    return location


def make_location(name="Sunnyvale Badminton Center", **kwargs):
    return Location.objects.create(name=name, **kwargs)


def authed_client(user, location=None):
    """An APIClient with a fresh session token for `user` already attached.
    Defaults to the shared default_location() for non-staff users (a
    PlayerSession requires one); admins default to no location."""
    if location is None and not user.is_staff:
        location = default_location()
    session = PlayerSession.objects.create(user=user, location=location)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {session.key}")
    return client


def make_court(name="Court 1", location=None, number=None, **kwargs):
    if location is None:
        location = default_location()
    if number is None:
        number = (location.courts.aggregate(m=Max("number"))["m"] or 0) + 1
    return Court.objects.create(location=location, number=number, name=name, **kwargs)


def pair_for(entry, username):
    """The Pair within `entry` that has `username` as one of its 2 players."""
    return entry.pairs.get(Q(player_1__username=username) | Q(player_2__username=username))


def credential(username, password="pw12345"):
    """Shorthand for the {"username", "password"} shape create_queue_entry
    and join_open_slot now expect for each pair member."""
    return {"username": username, "password": password}


def future_expiry():
    return timezone.now() + timezone.timedelta(hours=1)


def past_expiry():
    return timezone.now() - timezone.timedelta(hours=1)
