from rest_framework.permissions import BasePermission


class TempAccountNotExpired(BasePermission):
    """Rejects requests from an authenticated user whose temp account has
    passed its end-of-day expiry, even if their token is still otherwise
    valid (enforced on every request, not just at login)."""

    message = "This temporary account has expired."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        profile = getattr(user, "player_profile", None)
        if profile is None:
            return True
        return not profile.is_expired
