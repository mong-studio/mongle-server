from rest_framework import serializers

from apps.tags.models import Tag
from apps.todos.models import Todo


class TodoSerializer(serializers.ModelSerializer):
    tag_id = serializers.PrimaryKeyRelatedField(
        source="tag",
        queryset=Tag.objects.all(),
        required=True,
    )
    tag_color = serializers.CharField(source="tag.color", read_only=True)
    tag_content = serializers.CharField(source="tag.content", read_only=True)
    quest = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = (
            "todo_id",
            "content",
            "status",
            "todo_date",
            "tag_id",
            "tag_color",
            "tag_content",
            "quest",
            "created_at",
        )
        read_only_fields = (
            "todo_id",
            "status",
            "tag_color",
            "tag_content",
            "quest",
            "created_at",
        )

    def get_quest(self, obj: Todo) -> dict[str, object] | None:
        quest = next(iter(obj.quests.all()), None)
        if quest is None:
            return None
        return {
            "quest_id": quest.quest_id,
            "content": quest.content,
            "character_id": quest.character_id,
            "character_name": quest.character.character_name,
        }
