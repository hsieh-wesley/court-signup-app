from django.db.models import Q
from django.utils import timezone

from .models import Membership, MembershipSnapshot


def active_membership(player, at=None):
    """The Membership row covering `at` (default: now), if any. Derived on
    every call, never stored — same philosophy as the derived Waiting Room
    player status."""
    if player is None:
        return None
    at = at or timezone.now()
    return (
        player.memberships.filter(starts_at__lte=at)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=at))
        .order_by("-starts_at")
        .first()
    )


def find_active_membership_by_phone(phone_number, at=None):
    """The currently-active Membership row (any player) for a phone number,
    if any — used by both member check-in and the admin-side "is this
    number already active on someone else" guard."""
    at = at or timezone.now()
    return (
        Membership.objects.filter(phone_number=phone_number, starts_at__lte=at)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=at))
        .select_related("player__user")
        .order_by("-starts_at")
        .first()
    )


def membership_status_for(user, at=None, location=None):
    """MembershipSnapshot.MEMBER / .NON_MEMBER for `user` at `at` (default:
    now), scoped to `location` when given — the value baked into
    LoginLog/CourtActivityLog rows at write time so history never
    reclassifies itself later. A membership scoped to a specific facility
    only counts as MEMBER for events at that facility; one scoped to "All
    Locations" (Membership.location=None) counts everywhere. Passing no
    `location` (e.g. an admin login with no facility context) checks
    membership globally, same as before location-scoping existed."""
    player = getattr(user, "player", None)
    membership = active_membership(player, at=at)
    if membership is None:
        return MembershipSnapshot.NON_MEMBER
    if location is not None and membership.location_id is not None and membership.location_id != location.id:
        return MembershipSnapshot.NON_MEMBER
    return MembershipSnapshot.MEMBER
