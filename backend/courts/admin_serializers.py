from django.db.models import Q
from rest_framework import serializers

from .models import Court, CourtActivityLog, Location, LoginLog, Pair, Player, QueueEntry


class AdminPlayerSerializer(serializers.ModelSerializer):
    """`status`/`court_number`/`checked_in_at` are computed from the
    `assignments`/`checkins` maps the view builds once per request (see
    admin_views._assignment_map/_checkin_map) rather than per-row, since a
    player list is otherwise an easy N+1. `status` is priority-derived and
    mutually exclusive: on_court > in_queue > waiting_room > not_checked_in.
    On Court/In Queue are global (a player can only be active/waiting at one
    facility at a time); Waiting Room/Not Checked In are evaluated against
    whichever `location_id` the request asked for."""

    username = serializers.SerializerMethodField()
    has_login = serializers.ReadOnlyField()
    login_active = serializers.SerializerMethodField()
    current_assignment = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    court_number = serializers.SerializerMethodField()
    checked_in_at = serializers.SerializerMethodField()

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
            "status",
            "court_number",
            "checked_in_at",
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
            .select_related("entry", "entry__court", "entry__court__location")
            .first()
        )
        if pair is None:
            return None
        return {
            "location": pair.entry.court.location.name,
            "court": pair.entry.court.name,
            "status": pair.entry.status,
        }

    def _assignment(self, player):
        if player.user_id is None:
            return None
        return self.context.get("assignments", {}).get(player.user_id)

    def get_status(self, player):
        if player.user_id is None:
            return "not_checked_in"
        assignment = self._assignment(player)
        if assignment:
            return "on_court" if assignment["status"] == QueueEntry.Status.ACTIVE else "in_queue"
        checked_in = player.user_id in self.context.get("checkins", {})
        return "waiting_room" if checked_in else "not_checked_in"

    def get_court_number(self, player):
        assignment = self._assignment(player)
        return assignment["court_number"] if assignment else None

    def get_checked_in_at(self, player):
        if player.user_id is None:
            return None
        return self.context.get("checkins", {}).get(player.user_id)


class AdminCourtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Court
        fields = ["id", "name", "number", "location", "capacity", "is_active"]


class AdminLocationSerializer(serializers.ModelSerializer):
    court_count = serializers.SerializerMethodField()
    active_court_count = serializers.SerializerMethodField()
    waiting_room_count = serializers.SerializerMethodField()
    in_queue_count = serializers.SerializerMethodField()
    on_court_count = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = [
            "id", "name", "is_active", "created_at", "court_count", "active_court_count",
            "waiting_room_count", "in_queue_count", "on_court_count",
        ]

    def get_court_count(self, location):
        return location.courts.count()

    def get_active_court_count(self, location):
        return location.courts.filter(is_active=True).count()

    def _counts(self, location):
        return self.context.get("location_counts", {}).get(
            location.id, {"waiting_room": 0, "in_queue": 0, "on_court": 0}
        )

    def get_waiting_room_count(self, location):
        return self._counts(location)["waiting_room"]

    def get_in_queue_count(self, location):
        return self._counts(location)["in_queue"]

    def get_on_court_count(self, location):
        return self._counts(location)["on_court"]


class LoginLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginLog
        fields = ["id", "username", "location_name", "context", "created_at"]


class CourtActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourtActivityLog
        fields = [
            "id", "event_type", "reason", "location_name", "court_number",
            "player_1_username", "player_2_username", "actor_username", "created_at",
        ]


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
    location_id = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    number = serializers.IntegerField(required=False, min_value=1, max_value=100)
    capacity = serializers.IntegerField(required=False, min_value=1)


class AdminBulkTestPlayersSerializer(serializers.Serializer):
    count = serializers.IntegerField(default=8, min_value=1, max_value=50)


class AdminLocationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    court_count = serializers.IntegerField(default=10, min_value=1, max_value=100)


class AdminLocationEditSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    is_active = serializers.BooleanField(required=False)


class AdminCourtCountSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=100)
