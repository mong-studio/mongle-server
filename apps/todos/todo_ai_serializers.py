from __future__ import annotations

from typing import Any

from rest_framework import serializers


class TaskCandidateSerializer(serializers.Serializer[dict[str, Any]]):
    title = serializers.CharField(max_length=20)
    due_date = serializers.DateField()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=20),
        allow_empty=True,
        required=False,
    )


class TodoGenerateRequestSerializer(serializers.Serializer[dict[str, Any]]):
    prompt = serializers.CharField(max_length=200)


class TodoChatRequestSerializer(serializers.Serializer[dict[str, Any]]):
    message = serializers.CharField(max_length=600)
    thread_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class TodoCommitRequestSerializer(serializers.Serializer[dict[str, Any]]):
    todos = TaskCandidateSerializer(many=True, required=False)
    calendar_events = TaskCandidateSerializer(many=True, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        todos = attrs.get("todos", [])
        events = attrs.get("calendar_events", [])
        if not todos and not events:
            raise serializers.ValidationError(
                "최소 한 개 이상의 TODO 또는 일정이 필요합니다."
            )
        return attrs


class QuestPreviewSerializer(serializers.Serializer[dict[str, Any]]):
    quest_id = serializers.UUIDField()
    content = serializers.CharField()
    character_id = serializers.UUIDField()


class SavedTodoSerializer(serializers.Serializer[dict[str, Any]]):
    todo_id = serializers.UUIDField()
    content = serializers.CharField()
    status = serializers.CharField()
    todo_date = serializers.DateField()
    tags = serializers.ListField(child=serializers.CharField())
    quest = QuestPreviewSerializer(allow_null=True)


class SavedScheduleSerializer(serializers.Serializer[dict[str, Any]]):
    schedule_id = serializers.UUIDField()
    title = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField(allow_null=True)
    tags = serializers.ListField(child=serializers.CharField())
