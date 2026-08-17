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


class Pair(models.Model):
    """Two players occupying one of a QueueEntry's 2 slots."""

    entry = models.ForeignKey(QueueEntry, on_delete=models.CASCADE, related_name="pairs")
    slot = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")])
    player_1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pairs_as_player1"
    )
    player_2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pairs_as_player2"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_pairs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slot"]
        constraints = [
            models.UniqueConstraint(fields=["entry", "slot"], name="unique_slot_per_entry"),
            models.CheckConstraint(
                condition=~models.Q(player_1=models.F("player_2")),
                name="pair_players_distinct",
            ),
        ]

    def __str__(self):
        return f"{self.entry} slot {self.slot}: {self.player_1.username} & {self.player_2.username}"
