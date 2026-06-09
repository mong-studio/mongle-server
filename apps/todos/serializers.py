from rest_framework import serializers

from apps.todos.models import Tag, Todo


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("tag_id", "content", "color")
        read_only_fields = ("tag_id",)


class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = (
            "todo_id",
            "content",
            "status",
            "todo_date",
            "created_at",
        )
        read_only_fields = ("todo_id", "status", "created_at")
