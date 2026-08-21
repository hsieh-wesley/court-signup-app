import datetime
import secrets

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


class Membership(models.Model):
    """A dated period during which a Player held member status. Never
    mutated to represent a *different* period — a lapsed-then-renewed
    membership gets a NEW row here, so period history stays intact and
    the same Player/User/username is reused rather than duplicated.
    'Currently a member' is derived (see services._active_membership),
    never stored as a flag on Player. At most one row per Player may be
    "current" at a time — enforced at the service layer, not the DB,
    since past (lapsed) rows must remain readable forever."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="memberships")
    phone_number = models.CharField(max_length=10)
    # Which facility this period is valid at; null means "All Locations".
    # PROTECT (like every other Location FK) so a facility with membership
    # history can't be hard-deleted out from under it.
    location = models.ForeignKey(
        "Location", null=True, blank=True, on_delete=models.PROTECT, related_name="memberships"
    )
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.player.display_name} ({self.starts_at.date()}–{self.expires_at.date() if self.expires_at else '…'})"


class MembershipSnapshot(models.TextChoices):
    """Written once, at the moment a LoginLog/CourtActivityLog row is
    created, from whatever Membership state was true right then — never
    re-derived later. This is what makes 'was this player a member at the
    time of this event' immune to a later edit/expiration of their
    Membership: the row keeps whatever was baked in, forever. Same
    snapshot philosophy CourtActivityLog already uses for its other
    fields (location_name, court_number, player usernames, etc)."""

    MEMBER = "member", "Member"
    NON_MEMBER = "non_member", "Non-member"


class Location(models.Model):
    """A physical venue. Owns its own Courts; court numbers are only unique
    within a Location, not globally."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Court(models.Model):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="courts")
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(
        default=settings.COURT_CAPACITY_DEFAULT
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["location", "number"], name="unique_court_number_per_location"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"Court {self.number}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.location.name} — {self.name}"


class PlayerSession(models.Model):
    """An authenticated, persistent session — admin-only under the public
    kiosk model. Regular players never hold one: every kiosk action
    (join/unsign/status) verifies credentials fresh instead. See
    services.create_player_session and services.verify_pair_credentials."""

    key = models.CharField(max_length=40, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.CASCADE, related_name="sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(20)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} @ {self.location.name if self.location else '—'}"


class LoginLog(models.Model):
    """Append-only. Never edited or deleted.

    Player authentication history for events NOT already fully represented
    by a CourtActivityLog row — a successful court join already names both
    players + facility + timestamp there, so logging it again here would be
    redundant. Reserved for: an admin's persistent-session login, a My
    Status credential check, account registration (a point-in-time fact
    about where an account was created, not a stored relationship — the
    Player itself stays global and usable at any facility), and a
    same-day facility check-in (explicit, or implied by the player's
    first Sign Up/Join at a facility that day). REGISTRATION and CHECK_IN
    rows are also what the derived Waiting Room status is computed from —
    see AdminPlayerSerializer.get_status."""

    class Context(models.TextChoices):
        ADMIN_LOGIN = "admin_login", "Admin login"
        STATUS_CHECK = "status_check", "Status check"
        REGISTRATION = "registration", "Registration"
        CHECK_IN = "check_in", "Check-in"
        MEMBER_CHECK_IN = "member_check_in", "Member check-in"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="login_logs"
    )
    username = models.CharField(max_length=150)
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.PROTECT, related_name="login_logs"
    )
    location_name = models.CharField(max_length=100, blank=True)
    context = models.CharField(
        max_length=20, choices=Context.choices, default=Context.ADMIN_LOGIN
    )
    membership_status = models.CharField(
        max_length=20, choices=MembershipSnapshot.choices, default=MembershipSnapshot.NON_MEMBER
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


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


class CourtActivityLog(models.Model):
    """Append-only. Never edited or deleted. Uses ID + snapshot fields so a
    row still reads correctly after a later rename/deactivation elsewhere.
    `pair` is SET_NULL (Pair rows are actually hard-deleted); every other FK
    is PROTECT since nothing else in this app is ever hard-deleted."""

    class EventType(models.TextChoices):
        PAIR_QUEUED = "pair_queued", "Pair queued"
        PAIR_ACTIVATED = "pair_activated", "Pair activated"
        OPEN_SLOT_JOINED = "open_slot_joined", "Open slot joined"
        PAIR_ENDED = "pair_ended", "Pair ended"
        COURT_DROPPED = "court_dropped", "Court dropped"
        COURT_DEACTIVATED = "court_deactivated", "Court deactivated"
        COURT_REACTIVATED = "court_reactivated", "Court reactivated"

    class Reason(models.TextChoices):
        UNSIGNED = "unsigned", "Unsigned"
        ADMIN_REMOVED = "admin_removed", "Admin removed"
        PLAYER_DEACTIVATED = "player_deactivated", "Player deactivated"
        COURT_DROPPED = "court_dropped", "Court dropped"
        COURT_DEACTIVATED = "court_deactivated", "Court deactivated"
        EXPIRED = "expired", "Expired"

    event_type = models.CharField(max_length=30, choices=EventType.choices)
    reason = models.CharField(max_length=30, choices=Reason.choices, blank=True)

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="activity_logs")
    location_name = models.CharField(max_length=100)
    court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="activity_logs")
    court_number = models.PositiveSmallIntegerField()
    entry = models.ForeignKey(
        QueueEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="activity_logs"
    )
    pair = models.ForeignKey(
        Pair, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_logs"
    )

    player_1_username = models.CharField(max_length=150, blank=True)
    player_2_username = models.CharField(max_length=150, blank=True)
    actor_username = models.CharField(max_length=150, blank=True)
    # Two fields, not one — a pair event involves two independent players
    # who can have different membership statuses at that moment (mirrors
    # the existing player_1_username/player_2_username split, snapshotted
    # the same way).
    player_1_membership_status = models.CharField(
        max_length=20, choices=MembershipSnapshot.choices, blank=True, default=""
    )
    player_2_membership_status = models.CharField(
        max_length=20, choices=MembershipSnapshot.choices, blank=True, default=""
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
