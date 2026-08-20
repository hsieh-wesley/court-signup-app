from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Simple foundation for a Player vs. Administrator distinction — reuses
    Django's built-in is_staff flag rather than a new role field/framework.
    Covers both the `admin` and `staff` accounts — they're both is_staff;
    only is_superuser (see IsSuperUser below) tells them apart."""

    message = "Administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


class IsSuperUser(BasePermission):
    """The subset of admin actions `staff` cannot do — creating a brand-new
    facility, resetting staff's own password — reusing Django's built-in
    is_superuser flag rather than a new role field."""

    message = "This action requires the admin account."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
