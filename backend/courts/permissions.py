from rest_framework.permissions import BasePermission


class TempAccountNotExpired(BasePermission):
    """Rejects requests from an authenticated user whose account has an
    expiry set and has passed it, even if their token is still otherwise
    valid (enforced on every request, not just at login). A Player with no
    expires_at (the default for admin-created accounts) never expires."""

    message = "This account has expired."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        player = getattr(user, "player", None)
        if player is None:
            return True
        return not player.is_expired


class IsAdmin(BasePermission):
    """Simple foundation for a Player vs. Administrator distinction — reuses
    Django's built-in is_staff flag rather than a new role field/framework."""

    message = "Administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
