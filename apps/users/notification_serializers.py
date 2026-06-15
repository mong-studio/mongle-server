from rest_framework import serializers

from apps.users.models import Notification


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    class Meta:
        model = Notification
        fields = (
            "notification_id",
            "type",
            "title",
            "content",
            "is_read",
            "data",
            "created_at",
        )
        read_only_fields = fields
