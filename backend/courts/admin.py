from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Court, Pair, Player, QueueEntry

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


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "is_active")


class PairInline(admin.TabularInline):
    model = Pair
    extra = 0
    fields = ("slot", "player_1", "player_2", "created_by")


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "court", "status", "created_at", "expires_at")
    list_filter = ("court", "status")
    inlines = [PairInline]
