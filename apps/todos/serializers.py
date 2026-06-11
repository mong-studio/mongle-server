from rest_framework import serializers

from apps.tags.models import Tag
from apps.todos.models import Todo


class TodoSerializer(serializers.ModelSerializer):
    tag_id = serializers.PrimaryKeyRelatedField(
        source="tag",
        queryset=Tag.objects.all(),
        required=False,
    )
    tag_color = serializers.CharField(source="tag.color", read_only=True)
    tag_content = serializers.CharField(source="tag.content", read_only=True)

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
            "created_at",
        )
        read_only_fields = (
            "todo_id",
            "status",
            "tag_color",
            "tag_content",
            "created_at",
        )
