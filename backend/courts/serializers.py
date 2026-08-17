from django.conf import settings
from rest_framework import serializers

from .models import Court, QueueEntry


class QueueEntrySerializer(serializers.ModelSerializer):
    members = serializers.SlugRelatedField(
        slug_field="username", many=True, read_only=True
    )
    court = serializers.SlugRelatedField(slug_field="name", read_only=True)
    seconds_remaining = serializers.SerializerMethodField()

    class Meta:
        model = QueueEntry
        fields = [
            "id",
            "court",
            "members",
            "status",
            "created_at",
            "activated_at",
            "expires_at",
            "ended_at",
            "seconds_remaining",
        ]

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
    usernames = serializers.ListField(
        child=serializers.CharField(max_length=150), allow_empty=False
    )

    def validate_usernames(self, value):
        if len(value) not in settings.ALLOWED_GROUP_SIZES:
            raise serializers.ValidationError(
                f"Group size must be one of {settings.ALLOWED_GROUP_SIZES}."
            )
        return value


class UnsignSerializer(serializers.Serializer):
    usernames = serializers.ListField(
        child=serializers.CharField(max_length=150), allow_empty=False
    )

    def validate_usernames(self, value):
        if len(value) % 2 != 0:
            raise serializers.ValidationError(
                "Must unsign an even number of players (at least 2 at a time)."
            )
        return value
