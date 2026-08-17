import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_expires_at():
    """End of the current day (local time) — temp accounts expire at midnight."""
    now = timezone.localtime()
    end_of_day = datetime.datetime.combine(now.date(), datetime.time(23, 59, 59))
    return timezone.make_aware(end_of_day, timezone.get_current_timezone())


class PlayerProfile(models.Model):
    """Extends a temp auth.User with an end-of-day expiry."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="player_profile"
    )
    display_name = models.CharField(max_length=100, blank=True)
    expires_at = models.DateTimeField(default=default_expires_at)

    def __str__(self):
        return f"{self.user.username} (expires {self.expires_at:%Y-%m-%d %H:%M})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class Court(models.Model):
    name = models.CharField(max_length=100, unique=True)
    capacity = models.PositiveSmallIntegerField(
        default=settings.COURT_CAPACITY_DEFAULT
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class QueueEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="queue_entries")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="queue_entries")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_queue_entries",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.court.name} #{self.pk} ({self.status})"
