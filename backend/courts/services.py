import datetime
import re

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import activity_log
from .membership import find_active_membership_by_phone
from .models import Court, CourtActivityLog, LoginLog, Membership, Pair, PlayerSession, QueueEntry
from .password_gen import generate_member_password

User = get_user_model()

USERNAME_RE = re.compile(r"^[A-Za-z]{1,20}$")


class ServiceError(Exception):
    """Raised for business-rule violations; views translate this to a JSON
    error response using `status` (default 400)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _reservation_expiry(now):
    return now + datetime.timedelta(minutes=settings.RESERVATION_DURATION_MINUTES)


def _promote_next_if_free(court):
    """Activate the oldest waiting entry if the court has no active entry."""
    if QueueEntry.objects.filter(court=court, status=QueueEntry.Status.ACTIVE).exists():
        return
    next_entry = (
        QueueEntry.objects.select_for_update()
        .filter(court=court, status=QueueEntry.Status.WAITING)
        .order_by("created_at", "id")
        .first()
    )
    if next_entry is None:
        return
    now = timezone.now()
    next_entry.status = QueueEntry.Status.ACTIVE
    next_entry.activated_at = now
    next_entry.expires_at = _reservation_expiry(now)
    next_entry.save()
    for pair in next_entry.pairs.select_related("player_1", "player_2").all():
        activity_log.log_pair_event(
            CourtActivityLog.EventType.PAIR_ACTIVATED, court, next_entry, pair
        )


def reap_expired_reservations(court_ids=None):
    """Close out any active reservation whose time is up and promote the next
    waiting entry. Called lazily on every board read and before/after
    join/unsign, rather than via a background worker (see plan TODO)."""
    courts = Court.objects.all()
    if court_ids is not None:
        courts = courts.filter(id__in=court_ids)

    for court in courts:
        with transaction.atomic():
            locked_court = Court.objects.select_for_update().get(pk=court.pk)
            active = (
                QueueEntry.objects.select_for_update()
                .filter(court=locked_court, status=QueueEntry.Status.ACTIVE)
                .first()
            )
            if active and active.expires_at and active.expires_at <= timezone.now():
                for pair in active.pairs.select_related("player_1", "player_2").all():
                    activity_log.log_pair_event(
                        CourtActivityLog.EventType.PAIR_ENDED,
                        locked_court,
                        active,
                        pair,
                        reason=CourtActivityLog.Reason.EXPIRED,
                    )
                active.status = QueueEntry.Status.EXPIRED
                active.ended_at = timezone.now()
                active.save()
            _promote_next_if_free(locked_court)


def _conflicting_usernames(locked_court, usernames):
    """Usernames among `usernames` already waiting/active on this court."""
    existing_pairs = Pair.objects.filter(
        entry__court=locked_court,
        entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
    ).select_related("player_1", "player_2")
    existing_usernames = set()
    for pair in existing_pairs:
        existing_usernames.add(pair.player_1.username)
        existing_usernames.add(pair.player_2.username)
    return sorted(existing_usernames & set(usernames))


def create_queue_entry(court, pairs, created_by):
    """`pairs` is a list of 1 or 2 [username, username] groups."""
    if not court.is_active or not court.location.is_active:
        raise ServiceError(f"{court.name} is not currently available.")
    if len(pairs) not in (1, 2):
        raise ServiceError("Must submit 1 or 2 pairs.")
    for group in pairs:
        if len(group) != 2:
            raise ServiceError("Each pair must have exactly 2 players.")

    flat = [username for group in pairs for username in group]
    if len(flat) not in settings.ALLOWED_GROUP_SIZES:
        raise ServiceError(
            f"Group size must be one of {settings.ALLOWED_GROUP_SIZES}, got {len(flat)}."
        )
    if len(set(flat)) != len(flat):
        raise ServiceError("Duplicate usernames in the same group are not allowed.")
    if created_by.username not in flat:
        raise ServiceError("The signing-in user must be included in their own group.")

    users_by_username = {u.username: u for u in User.objects.filter(username__in=flat)}
    missing = set(flat) - users_by_username.keys()
    if missing:
        raise ServiceError(f"Unknown username(s): {', '.join(sorted(missing))}.")

    reap_expired_reservations(court_ids=[court.id])

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)

        conflicting_names = _conflicting_usernames(locked_court, flat)
        if conflicting_names:
            raise ServiceError(
                f"Already signed up on {locked_court.name}: {', '.join(conflicting_names)}."
            )

        entry = QueueEntry.objects.create(
            court=locked_court, created_by=created_by, status=QueueEntry.Status.WAITING
        )
        created_pairs = []
        for slot, group in enumerate(pairs, start=1):
            pair = Pair.objects.create(
                entry=entry,
                slot=slot,
                player_1=users_by_username[group[0]],
                player_2=users_by_username[group[1]],
                created_by=created_by,
            )
            created_pairs.append(pair)

        _promote_next_if_free(locked_court)

        entry.refresh_from_db()
        if entry.status == QueueEntry.Status.WAITING:
            for pair in created_pairs:
                activity_log.log_pair_event(
                    CourtActivityLog.EventType.PAIR_QUEUED, locked_court, entry, pair
                )

    entry.refresh_from_db()
    return entry


def join_open_slot(entry, usernames, requesting_user):
    """Fill a WAITING entry's one remaining open slot with a new pair.

    Locks Court then QueueEntry, same order as every other write path here,
    so a join can never race a promotion of the same entry: whichever
    transaction commits first is authoritative, and the other re-reads
    entry.status/pairs under its own lock and fails cleanly instead of
    double-filling a slot.
    """
    if not entry.court.is_active or not entry.court.location.is_active:
        raise ServiceError(f"{entry.court.name} is not currently available.")
    if len(usernames) != 2:
        raise ServiceError("A joining group must be exactly one pair (2 players).")
    if len(set(usernames)) != 2:
        raise ServiceError("Duplicate usernames in the same group are not allowed.")
    if requesting_user.username not in usernames:
        raise ServiceError("The signing-in user must be included in their own pair.")

    users_by_username = {u.username: u for u in User.objects.filter(username__in=usernames)}
    missing = set(usernames) - users_by_username.keys()
    if missing:
        raise ServiceError(f"Unknown username(s): {', '.join(sorted(missing))}.")

    court = entry.court
    reap_expired_reservations(court_ids=[court.id])

    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=court.pk)
        locked_entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)

        if locked_entry.status != QueueEntry.Status.WAITING:
            raise ServiceError("This position is no longer open to join.")

        occupied_slots = set(locked_entry.pairs.values_list("slot", flat=True))
        if len(occupied_slots) >= 2:
            raise ServiceError("This position is already full.")
        open_slot = 1 if 1 not in occupied_slots else 2

        conflicting_names = _conflicting_usernames(locked_court, usernames)
        if conflicting_names:
            raise ServiceError(
                f"Already signed up on {locked_court.name}: {', '.join(conflicting_names)}."
            )

        pair = Pair.objects.create(
            entry=locked_entry,
            slot=open_slot,
            player_1=users_by_username[usernames[0]],
            player_2=users_by_username[usernames[1]],
            created_by=requesting_user,
        )
        activity_log.log_pair_event(
            CourtActivityLog.EventType.OPEN_SLOT_JOINED, locked_court, locked_entry, pair
        )

    entry.refresh_from_db()
    return entry


def _end_pair(locked_court, locked_entry, pair, reason, actor=None):
    """Delete one pair from an entry whose Court+QueueEntry the caller
    already holds select_for_update() locks on, logging why before it's
    gone. If it was the entry's last pair, close out the entry
    (completed/cancelled) and promote the next waiting entry if it was
    active. Shared by the player-initiated `unsign_pair` and the
    admin-initiated removal actions."""
    activity_log.log_pair_event(
        CourtActivityLog.EventType.PAIR_ENDED, locked_court, locked_entry, pair,
        reason=reason, actor=actor,
    )
    pair.delete()
    remaining = locked_entry.pairs.count()

    if remaining == 0:
        was_active = locked_entry.status == QueueEntry.Status.ACTIVE
        locked_entry.status = (
            QueueEntry.Status.COMPLETED if was_active else QueueEntry.Status.CANCELLED
        )
        locked_entry.ended_at = timezone.now()
        locked_entry.save()
        if was_active:
            _promote_next_if_free(locked_court)


def unsign_pair(entry, pair_id, requesting_user):
    """Remove one whole pair from an entry. Any current member of the entry
    may unsign any pair, not just their own — matches the trust model of
    the original flat-membership unsign."""
    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=entry.court_id)
        locked_entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)

        current_usernames = set()
        for pair in locked_entry.pairs.all():
            current_usernames.add(pair.player_1.username)
            current_usernames.add(pair.player_2.username)
        if requesting_user.username not in current_usernames:
            raise ServiceError("You are not a member of this group.")
        if locked_entry.status not in (QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE):
            raise ServiceError("This entry is no longer active or waiting.")

        try:
            pair = locked_entry.pairs.get(pk=pair_id)
        except Pair.DoesNotExist:
            raise ServiceError("That pair is not part of this entry.")

        _end_pair(locked_court, locked_entry, pair, reason=CourtActivityLog.Reason.UNSIGNED)

    entry.refresh_from_db()
    return entry


def _find_shared_pair(user_a, user_b):
    """The active/waiting Pair containing exactly these two players, if any."""
    return (
        Pair.objects.filter(
            Q(player_1=user_a, player_2=user_b) | Q(player_1=user_b, player_2=user_a),
            entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
        )
        .select_related("entry")
        .first()
    )


def unsign_by_credentials(pairs_credentials):
    """Quick-unsign entry point: 1 or 2 groups of 2 {"username","password"}
    dicts — same shape verify_pair_credentials/create_queue_entry take, so
    the Overview widget can reuse its 2-vs-4 toggle. Every credential is
    verified and both pairs resolved *before* anything is touched; for a
    4-player unsign, the two pairs must belong to the same QueueEntry —
    being on the same physical court is not enough, since a court can host
    two distinct QueueEntry groups (e.g. one active, one waiting)."""
    verified_pairs = []
    for group in pairs_credentials:
        u_a = verify_credential(group[0]["username"], group[0]["password"])
        u_b = verify_credential(group[1]["username"], group[1]["password"])
        pair = _find_shared_pair(u_a, u_b)
        if pair is None:
            raise ServiceError(f"{u_a.username} and {u_b.username} aren't signed up together.")
        verified_pairs.append(pair)

    if len(verified_pairs) == 2 and verified_pairs[0].entry_id != verified_pairs[1].entry_id:
        raise ServiceError("Those two pairs aren't signed up as the same group.")

    entry = verified_pairs[0].entry
    with transaction.atomic():
        locked_court = Court.objects.select_for_update().get(pk=entry.court_id)
        locked_entry = QueueEntry.objects.select_for_update().get(pk=entry.pk)
        for pair in verified_pairs:
            try:
                locked_pair = locked_entry.pairs.get(pk=pair.pk)
            except Pair.DoesNotExist:
                raise ServiceError("That pair is no longer part of this entry.")
            _end_pair(locked_court, locked_entry, locked_pair, reason=CourtActivityLog.Reason.UNSIGNED)
    entry.refresh_from_db()
    return entry


def _check_not_expired(user):
    player = getattr(user, "player", None)
    if player is not None and player.is_expired:
        raise ServiceError("This account has expired.", status=403)


def _reject_if_active_elsewhere(user, target_court):
    """A player can't be active/waiting on two courts at once — not even
    two courts at the same facility. Excludes only the exact court being
    targeted (not the whole facility), so retrying the SAME court still
    falls through to _conflicting_usernames' more specific "already
    signed up on X" message instead of this generic one firing first.
    Under the public-kiosk model there's no login moment to check this
    at, so it's enforced here — at the point of joining — instead."""
    conflict = (
        Pair.objects.filter(
            Q(player_1=user) | Q(player_2=user),
            entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
        )
        .exclude(entry__court=target_court)
        .select_related("entry__court__location")
        .first()
    )
    if conflict:
        loc = conflict.entry.court.location
        court = conflict.entry.court
        raise ServiceError(
            f"{user.username} is still signed in at {loc.name} (Court {court.number}).",
            status=409,
        )


def verify_credential(username, password):
    """Verifies one player's identity fresh, for actions with no persisted
    session to rely on (unsign, status check). Raises ServiceError if the
    credentials are wrong or the account has expired."""
    user = authenticate(username=username, password=password)
    if user is None:
        raise ServiceError(f"Incorrect username or password for {username}.")
    _check_not_expired(user)
    return user


def has_facility_presence_today(user, location):
    """Whether `user` already has a valid registration/check-in LoginLog for
    `location` today — the same query the derived Waiting Room status
    (AdminPlayerSerializer.get_status) is computed from, shared here so a
    Sign Up/Join never writes a duplicate presence row."""
    if location is None:
        return False
    return LoginLog.objects.filter(
        user=user,
        location=location,
        context__in=[
            LoginLog.Context.REGISTRATION,
            LoginLog.Context.CHECK_IN,
            LoginLog.Context.MEMBER_CHECK_IN,
        ],
        created_at__date=timezone.localdate(),
    ).exists()


def verify_pair_credentials(pairs_credentials, target_court):
    """`pairs_credentials` is a list of 1-2 groups, each a list of 2
    {"username", "password"} dicts. Every member's credentials are verified
    — there is no "self" exemption, since the public kiosk has no notion of
    who's already signed in. Also enforces the single-court invariant for
    each verified player against `target_court` (a player can only ever be
    active/waiting on one court anywhere at a time), and — since Sign Up
    and Join This Pair are the only two flows that route through here —
    stamps a same-day check-in for anyone who doesn't already have a valid
    one, so a player never has to tap Check In separately just to show up
    on a court. Returns the equivalent plain [[username, username], ...]
    structure for services.create_queue_entry / join_open_slot, which are
    unchanged."""
    target_location = target_court.location
    result = []
    for group in pairs_credentials:
        usernames = []
        for member in group:
            username = member.get("username", "")
            password = member.get("password", "")
            user = verify_credential(username, password)
            _reject_if_active_elsewhere(user, target_court)
            if not has_facility_presence_today(user, target_location):
                activity_log.log_player_auth_event(user, target_location, LoginLog.Context.CHECK_IN)
            usernames.append(username)
        result.append(usernames)
    return result


def validate_new_username(username, exclude_user_id=None):
    """Shared by self-registration and every admin username-creating path.
    1-20 letters only. "Protected" names — case-insensitive — are "admin",
    every current staff username, and every username whose Player
    currently has an active Membership (not "ever was a member" — a
    lapsed member's username stays taken via ordinary uniqueness, but
    stops being specially protected). Uniqueness itself is also
    case-insensitive, so "Alice" and "alice" can never both exist.
    `exclude_user_id` excludes that user from BOTH checks — editing an
    account to (re-)claim a name it already legitimately holds (e.g. a
    member re-saving their own protected username unchanged) is not a
    collision with itself."""
    if not USERNAME_RE.match(username):
        raise ServiceError("Username must be 1-20 letters, no numbers or symbols.")

    now = timezone.now()
    active_memberships = (
        Membership.objects.filter(starts_at__lte=now)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .exclude(player__user_id=exclude_user_id or 0)
        .values_list("player__user__username", flat=True)
    )
    reserved = {"admin", *User.objects.filter(is_staff=True).exclude(pk=exclude_user_id or 0)
                .values_list("username", flat=True)}
    reserved |= {u for u in active_memberships if u}
    if username.lower() in {r.lower() for r in reserved}:
        raise ServiceError(f"'{username}' is a protected name and can't be used.")

    qs = User.objects.filter(username__iexact=username)
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    if qs.exists():
        raise ServiceError(f"Username '{username}' is already taken.")


def member_check_in(phone_number, location):
    """Phone-only check-in for a member: no password. Draws a fresh
    animal-only password (invalidating whatever they had before), stamps
    a MEMBER_CHECK_IN LoginLog row, and returns it for one-time display.
    No PlayerSession/token is created — same stateless-kiosk model as
    every other public action here."""
    membership = find_active_membership_by_phone(phone_number)
    if membership is None or membership.player.user is None:
        raise ServiceError("No member found with that phone number.")
    user = membership.player.user
    _check_not_expired(user)
    plaintext = generate_member_password()
    user.set_password(plaintext)
    user.save()
    activity_log.log_player_auth_event(user, location, LoginLog.Context.MEMBER_CHECK_IN)
    return user, plaintext


def create_player_session(user, location=None):
    """Admin-only. Regular players never hold a persistent session under
    the public-kiosk model — every kiosk action verifies credentials fresh
    instead (see verify_pair_credentials/verify_credential above). Admins
    may hold multiple concurrent sessions (e.g. multiple devices/tabs) —
    no single-session limit applies to them, so a new login never deletes
    an existing admin session."""
    if not user.is_staff:
        raise ServiceError("Player accounts do not use persistent sessions.")
    session = PlayerSession.objects.create(user=user, location=location)
    activity_log.log_player_auth_event(user, location, LoginLog.Context.ADMIN_LOGIN)
    return session
