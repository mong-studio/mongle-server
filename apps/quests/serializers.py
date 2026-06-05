from rest_framework import serializers

from apps.quests.models import Quest


class QuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quest
        fields = ("quest_id", "character", "todo", "content", "created_at")
        read_only_fields = ("quest_id", "created_at")
