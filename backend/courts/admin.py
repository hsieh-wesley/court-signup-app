from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Court, PlayerProfile, QueueEntry

User = get_user_model()


class PlayerProfileInline(admin.StackedInline):
    model = PlayerProfile
    can_delete = False
    extra = 1
    max_num = 1


class TempUserAdmin(UserAdmin):
    inlines = [PlayerProfileInline]
    list_display = ("username", "is_staff", "player_profile_expires_at")

    @admin.display(description="Temp account expires")
    def player_profile_expires_at(self, obj):
        profile = getattr(obj, "player_profile", None)
        return profile.expires_at if profile else "—"


admin.site.unregister(User)
admin.site.register(User, TempUserAdmin)


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "is_active")


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "court", "status", "created_at", "expires_at")
    list_filter = ("court", "status")
    filter_horizontal = ("members",)
