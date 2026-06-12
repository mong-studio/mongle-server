"""TODO list/detail + AI bridge views."""

from __future__ import annotations

from secrets import compare_digest

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.characters.models import Character
from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.ai_client import TodoAIClient, TodoAIClientError
from apps.todos.models import Schedule, Todo
from apps.todos.serializers import TodoSerializer
from apps.todos.todo_ai_serializers import (
    SavedScheduleSerializer,
    SavedTodoSerializer,
    TodoChatRequestSerializer,
    TodoCommitRequestSerializer,
    TodoGenerateRequestSerializer,
)
from apps.users.models import User


class InternalServiceTokenPermission(BasePermission):
    message = "유효한 내부 서비스 토큰이 필요합니다."

    def has_permission(self, request, view) -> bool:
        expected_token = settings.MONGLE_AI_API_KEY
        provided_token = request.headers.get("X-Internal-Service-Token", "")
        return bool(expected_token) and compare_digest(provided_token, expected_token)


class TodoListCreateView(generics.ListCreateAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        tag = serializer.validated_data.pop("tag", None)
        if tag is None:
            tag = Tag.objects.filter(tag_id=1).first()
        serializer.save(user=self.request.user, tag=tag)


class TodoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "todo_id"

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)


class TodoGenerateAIView(APIView):
    permission_classes = (InternalServiceTokenPermission,)

    def post(self, request) -> Response:
        serializer = TodoGenerateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _resolve_user(request)
        today = timezone.localdate().isoformat()

        try:
            result = _todo_ai_client().generate(
                user_id=str(user.user_id),
                prompt=serializer.validated_data["prompt"],
                today=today,
            )
        except TodoAIClientError as err:
            return Response({"error": str(err)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class TodoChatAIView(APIView):
    permission_classes = (InternalServiceTokenPermission,)

    def post(self, request) -> Response:
        serializer = TodoChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _resolve_user(request)
        today = timezone.localdate().isoformat()

        try:
            result = _todo_ai_client().chat(
                user_id=str(user.user_id),
                message=serializer.validated_data["message"],
                today=today,
                thread_id=serializer.validated_data.get("thread_id") or None,
            )
        except TodoAIClientError as err:
            return Response({"error": str(err)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class TodoCommitAIView(APIView):
    permission_classes = (InternalServiceTokenPermission,)

    def post(self, request) -> Response:
        serializer = TodoCommitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _resolve_user(request)
        today = timezone.localdate()
        todos_payload = serializer.validated_data.get("todos", [])
        events_payload = serializer.validated_data.get("calendar_events", [])

        saved_todos = [
            Todo.objects.create(
                user=user,
                tag=_ensure_tag(item.get("tags") or [], user),
                content=item["title"],
                todo_date=item["due_date"],
            )
            for item in todos_payload
        ]
        saved_events = [
            Schedule.objects.create(
                user=user,
                tag=_ensure_tag(item.get("tags") or [], user),
                title=item["title"],
                start_date=item["due_date"],
                end_date=item["due_date"],
            )
            for item in events_payload
        ]

        quests_by_todo: dict[str, Quest] = {}
        quest_triggered = False
        todays_todos = [todo for todo in saved_todos if todo.todo_date == today]
        active_characters = list(Character.objects.filter(user=user, is_active=True))
        if todays_todos and active_characters:
            remaining_daily_quota = max(
                0,
                5
                - Quest.objects.filter(todo__user=user, todo__todo_date=today).count(),
            )
            if remaining_daily_quota > 0:
                try:
                    generated = _todo_ai_client().generate_quests(
                        todos=[{"todo_id": str(todo.todo_id)} for todo in todays_todos],
                        characters=[
                            {
                                "character_id": str(character.character_id),
                                "name": character.character_name,
                                "persona": character.persona,
                            }
                            for character in active_characters
                        ],
                        remaining_daily_quota=remaining_daily_quota,
                    )
                except TodoAIClientError:
                    generated = {"generated": []}

                for item in generated.get("generated", []):
                    todo_id = str(item["todo_id"])
                    todo = next(
                        (row for row in todays_todos if str(row.todo_id) == todo_id),
                        None,
                    )
                    character = next(
                        (
                            row
                            for row in active_characters
                            if str(row.character_id) == str(item["character_id"])
                        ),
                        None,
                    )
                    if todo is None or character is None:
                        continue
                    quest = Quest.objects.create(
                        todo=todo,
                        character=character,
                        content=item["quest_text"],
                    )
                    quests_by_todo[todo_id] = quest
                    quest_triggered = True

        todo_data = SavedTodoSerializer(
            [
                {
                    "todo_id": todo.todo_id,
                    "content": todo.content,
                    "status": todo.status,
                    "todo_date": todo.todo_date,
                    "tags": [todo.tag.content],
                    "quest": (
                        {
                            "quest_id": quests_by_todo[str(todo.todo_id)].quest_id,
                            "content": quests_by_todo[str(todo.todo_id)].content,
                            "character_id": quests_by_todo[
                                str(todo.todo_id)
                            ].character_id,
                        }
                        if str(todo.todo_id) in quests_by_todo
                        else None
                    ),
                }
                for todo in saved_todos
            ],
            many=True,
        ).data
        schedule_data = SavedScheduleSerializer(
            [
                {
                    "schedule_id": event.schedule_id,
                    "title": event.title,
                    "start_date": event.start_date,
                    "end_date": event.end_date,
                    "tags": [event.tag.content],
                }
                for event in saved_events
            ],
            many=True,
        ).data
        return Response(
            {
                "todos": todo_data,
                "calendar_events": schedule_data,
                "quest_distribution_triggered": quest_triggered,
            },
            status=status.HTTP_201_CREATED,
        )


class TodoCompleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, todo_id) -> Response:
        todo = generics.get_object_or_404(Todo, todo_id=todo_id, user=request.user)
        if todo.status != Todo.Status.IN_PROGRESS:
            return Response(
                {"error": "완료할 수 없는 상태입니다."},
                status=status.HTTP_409_CONFLICT,
            )

        todo.status = Todo.Status.COMPLETED
        todo.save(update_fields=["status", "updated_at"])

        quest = todo.quests.select_related("character").first()
        if quest:
            from apps.posts.tasks import generate_post_from_quest

            quest_id = str(quest.quest_id)
            transaction.on_commit(
                lambda: generate_post_from_quest.apply_async(args=[quest_id])
            )

        return Response({"todo_id": str(todo.todo_id), "status": todo.status})


def _todo_ai_client() -> TodoAIClient:
    return TodoAIClient(
        base_url=settings.MONGLE_AI_API_BASE,
        api_key=settings.MONGLE_AI_API_KEY,
        timeout_seconds=settings.MONGLE_AI_TIMEOUT_SECONDS,
    )


def _resolve_user(request) -> User:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user

    demo_user, _ = User.objects.get_or_create(
        email="demo@mongle.local",
        defaults={
            "user_name": "체험자",
            "job": "Demo",
            "birth": "2000-01-01",
            "is_aiconsent": False,
        },
    )
    return demo_user


def _ensure_tag(tags: list[str], user: User) -> Tag:
    content = (tags[0] if tags else "기타").strip()[:20] or "기타"
    existing = Tag.objects.filter(user=user, content=content).first()
    if existing is not None:
        return existing
    last_id = Tag.objects.aggregate(max_id=Max("tag_id"))["max_id"] or 0
    return Tag.objects.create(
        tag_id=last_id + 1,
        user=user,
        content=content,
        color="#E7D39F",
    )
