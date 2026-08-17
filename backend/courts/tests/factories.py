from django.contrib.auth import get_user_model
from django.utils import timezone

from courts.models import Court, PlayerProfile

User = get_user_model()


def make_user(username, expires_at=None):
    user = User.objects.create_user(username=username, password="pw12345")
    kwargs = {"user": user}
    if expires_at is not None:
        kwargs["expires_at"] = expires_at
    PlayerProfile.objects.create(**kwargs)
    return user


def make_court(name="Court 1", **kwargs):
    return Court.objects.create(name=name, **kwargs)


def future_expiry():
    return timezone.now() + timezone.timedelta(hours=1)


def past_expiry():
    return timezone.now() - timezone.timedelta(hours=1)
