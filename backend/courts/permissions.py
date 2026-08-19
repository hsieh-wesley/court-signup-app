from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Simple foundation for a Player vs. Administrator distinction — reuses
    Django's built-in is_staff flag rather than a new role field/framework."""

    message = "Administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
