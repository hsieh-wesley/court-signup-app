from django.db.models import Q
from rest_framework import serializers

from .models import Court, Pair, Player, QueueEntry


class AdminPlayerSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    has_login = serializers.ReadOnlyField()
    login_active = serializers.SerializerMethodField()
    current_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            "id",
            "display_name",
            "username",
            "has_login",
            "login_active",
            "is_active",
            "created_at",
            "current_assignment",
        ]

    def get_username(self, player):
        return player.user.username if player.user else None

    def get_login_active(self, player):
        return bool(player.user and player.user.is_active)

    def get_current_assignment(self, player):
        if player.user is None:
            return None
        pair = (
            Pair.objects.filter(
                Q(player_1=player.user) | Q(player_2=player.user),
                entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
            )
            .select_related("entry", "entry__court")
            .first()
        )
        if pair is None:
            return None
        return {"court": pair.entry.court.name, "status": pair.entry.status}


class AdminCourtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Court
        fields = ["id", "name", "capacity", "is_active"]


class AdminPlayerCreateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=100)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    enable_login = serializers.BooleanField(default=False)

    def validate(self, data):
        if data.get("enable_login") and not data.get("username"):
            raise serializers.ValidationError(
                "username is required when enable_login is true."
            )
        return data


class AdminPlayerEditSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=100, required=False)
    username = serializers.CharField(max_length=150, required=False)


class AdminAddLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


class AdminRemovePlayerSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


class AdminCourtCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    capacity = serializers.IntegerField(required=False, min_value=1)


class AdminBulkTestPlayersSerializer(serializers.Serializer):
    count = serializers.IntegerField(default=8, min_value=1, max_value=50)
