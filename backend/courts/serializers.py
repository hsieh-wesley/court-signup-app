from django.conf import settings
from rest_framework import serializers

from .models import Court, Pair, QueueEntry


class PairSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()

    class Meta:
        model = Pair
        fields = ["id", "slot", "players", "created_at"]

    def get_players(self, obj):
        return [obj.player_1.username, obj.player_2.username]


class QueueEntrySerializer(serializers.ModelSerializer):
    court = serializers.SlugRelatedField(slug_field="name", read_only=True)
    pairs = PairSerializer(many=True, read_only=True)
    open_slot = serializers.SerializerMethodField()
    seconds_remaining = serializers.SerializerMethodField()

    class Meta:
        model = QueueEntry
        fields = [
            "id",
            "court",
            "pairs",
            "status",
            "created_at",
            "activated_at",
            "expires_at",
            "ended_at",
            "seconds_remaining",
            "open_slot",
        ]

    def get_open_slot(self, obj):
        return obj.status == QueueEntry.Status.WAITING and len(obj.pairs.all()) == 1

    def get_seconds_remaining(self, obj):
        if obj.status != QueueEntry.Status.ACTIVE or not obj.expires_at:
            return None
        from django.utils import timezone

        delta = (obj.expires_at - timezone.now()).total_seconds()
        return max(0, int(delta))


class CourtBoardSerializer(serializers.ModelSerializer):
    active_entry = serializers.SerializerMethodField()
    waiting_entries = serializers.SerializerMethodField()

    class Meta:
        model = Court
        fields = ["id", "name", "capacity", "is_active", "active_entry", "waiting_entries"]

    def get_active_entry(self, court):
        entry = court.queue_entries.filter(status=QueueEntry.Status.ACTIVE).first()
        return QueueEntrySerializer(entry).data if entry else None

    def get_waiting_entries(self, court):
        entries = court.queue_entries.filter(status=QueueEntry.Status.WAITING).order_by(
            "created_at", "id"
        )
        return QueueEntrySerializer(entries, many=True).data


class CreateQueueEntrySerializer(serializers.Serializer):
    court_id = serializers.PrimaryKeyRelatedField(queryset=Court.objects.all())
    pairs = serializers.ListField(
        child=serializers.ListField(
            child=serializers.CharField(max_length=150), min_length=2, max_length=2
        ),
        min_length=1,
        max_length=2,
    )

    def validate_pairs(self, value):
        flat = [username for group in value for username in group]
        if len(flat) not in settings.ALLOWED_GROUP_SIZES:
            raise serializers.ValidationError(
                f"Group size must be one of {settings.ALLOWED_GROUP_SIZES}."
            )
        return value


class JoinOpenSlotSerializer(serializers.Serializer):
    usernames = serializers.ListField(
        child=serializers.CharField(max_length=150), min_length=2, max_length=2
    )


class UnsignSerializer(serializers.Serializer):
    pair_id = serializers.IntegerField()
