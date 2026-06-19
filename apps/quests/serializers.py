from rest_framework import serializers

from apps.quests.models import Quest


class QuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quest
        fields = ("quest_id", "character", "todo", "content", "created_at")
        read_only_fields = ("quest_id", "created_at")


class QuestListItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="todo.content", read_only=True)
    due_date = serializers.DateField(source="todo.todo_date", read_only=True)

    class Meta:
        model = Quest
        fields = (
            "quest_id",
            "todo_id",
            "title",
            "status",
            "character_reaction",
            "due_date",
        )
