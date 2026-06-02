from rest_framework import serializers

from apps.todos.models import Todo


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
