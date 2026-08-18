import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_expires_at():
    """No longer used by any field — kept only because migrations/0001_initial.py
    references it as the historical default for PlayerProfile.expires_at, and
    Django's migration loader imports every migration file to build its graph.
    Removing this breaks makemigrations/migrate. Do not delete unless
    0001_initial.py is squashed."""
    now = timezone.localtime()
    end_of_day = datetime.datetime.combine(now.date(), datetime.time(23, 59, 59))
    return timezone.make_aware(end_of_day, timezone.get_current_timezone())


class Player(models.Model):
    """The canonical player/roster record. Login access (a linked auth.User)
    is optional and separate from being a player — a Player can exist with
    no login at all."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="player",
    )
    display_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.display_name

    @property
    def has_login(self):
        return self.user_id is not None

    @property
    def is_expired(self):
        return self.expires_at is not None and timezone.now() >= self.expires_at


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
