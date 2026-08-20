from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Court, CourtActivityLog, Location, LoginLog, Membership, Pair, Player, QueueEntry

User = get_user_model()


class PlayerInline(admin.StackedInline):
    model = Player
    can_delete = True
    extra = 0
    max_num = 1


class TempUserAdmin(UserAdmin):
    inlines = [PlayerInline]
    list_display = ("username", "is_staff", "player_display_name")

    @admin.display(description="Player")
    def player_display_name(self, obj):
        player = getattr(obj, "player", None)
        return player.display_name if player else "—"


admin.site.unregister(User)
admin.site.register(User, TempUserAdmin)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "has_login", "is_active", "expires_at")
    list_filter = ("is_active",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("player", "phone_number", "starts_at", "expires_at", "created_at")
    list_filter = ("starts_at",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "number", "capacity", "is_active")
    list_filter = ("location", "is_active")


class PairInline(admin.TabularInline):
    model = Pair
    extra = 0
    fields = ("slot", "player_1", "player_2", "created_by")


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "court", "status", "created_at", "expires_at")
    list_filter = ("court", "status")
    inlines = [PairInline]


@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ("username", "context", "location_name", "created_at")
    list_filter = ("context", "location")
    readonly_fields = [f.name for f in LoginLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CourtActivityLog)
class CourtActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "event_type", "reason", "location_name", "court_number",
        "player_1_username", "player_2_username", "actor_username", "created_at",
    )
    list_filter = ("event_type", "reason", "location")
    readonly_fields = [f.name for f in CourtActivityLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
