"""TODO list/detail + AI bridge views."""

from __future__ import annotations

import calendar as calendar_lib
from datetime import date
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.characters.models import Character
from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.ai_client import TodoAIClient, TodoAIClientError
from apps.todos.models import Schedule, Todo
from apps.todos.serializers import ScheduleSerializer, TodoSerializer
from apps.todos.todo_ai_serializers import (
    SavedScheduleSerializer,
    SavedTodoSerializer,
    TodoChatRequestSerializer,
    TodoCommitRequestSerializer,
    TodoConfirmRequestSerializer,
    TodoGenerateRequestSerializer,
    TodoQuestPreviewRequestSerializer,
)
from apps.users.models import User
from apps.users.notification_service import create_reflection_notification

logger = logging.getLogger(__name__)


class TodoListCreateView(generics.ListCreateAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = (
            Todo.objects.filter(user=self.request.user)
            .select_related("tag")
            .prefetch_related("quests__character")
            .order_by("-created_at")
        )
        todo_date = self.request.query_params.get("todo_date")
        if todo_date:
            queryset = queryset.filter(todo_date=todo_date)
        return queryset

    def perform_create(self, serializer):
        # 태그 미지정이면 태그 없이 생성한다(null).
        serializer.save(
            user=self.request.user,
            tag=serializer.validated_data.get("tag"),
        )


class TodoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "todo_id"

    def get_queryset(self):
        return (
            Todo.objects.filter(user=self.request.user)
            .select_related("tag")
            .prefetch_related("quests__character")
        )


class TodoGenerateAIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        serializer = TodoGenerateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        today = timezone.localdate().isoformat()

        try:
            result = _todo_ai_client().generate(
                user_id=str(user.user_id),
                prompt=serializer.validated_data["prompt"],
                today=today,
            )
        except TodoAIClientError as err:
            # 가짜로 분해하지 않는다. 프롬프트는 오직 실제 LLM(mongle-ai)으로만 간다.
            logger.warning("todo generate AI 호출 실패: %s", err)
            return Response(
                {
                    "error": {
                        "code": "AI_SERVICE_UNAVAILABLE",
                        "message": "AI 서버에 연결할 수 없어요. 다시 시도해주세요.",
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result, status=status.HTTP_200_OK)


class TodoChatAIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        serializer = TodoChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
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


class TodoPlannerConfirmView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        serializer = TodoCommitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _save_todo_candidates(request.user, serializer.validated_data)


def _save_todo_candidates(user: User, validated_data: dict) -> Response:
    todos_payload = validated_data.get("todos", [])
    events_payload = validated_data.get("calendar_events", [])
    today = timezone.localdate()
    candidates = [*todos_payload, *events_payload]
    todo_candidates = [item for item in candidates if item["due_date"] == today]
    event_candidates = [item for item in candidates if item["due_date"] != today]

    saved_todos = [
        Todo.objects.create(
            user=user,
            tag=_ensure_tag(item.get("tags") or [], user),
            content=item["title"],
            todo_date=item["due_date"],
        )
        for item in todo_candidates
    ]
    saved_events = [
        Schedule.objects.create(
            user=user,
            tag=_ensure_tag(item.get("tags") or [], user),
            title=item["title"],
            start_date=item["due_date"],
            end_date=item["due_date"],
        )
        for item in event_candidates
    ]

    quests_by_todo, quest_triggered = _assign_quests_to_todos(user, saved_todos)

    todo_data = SavedTodoSerializer(
        [_serialize_saved_todo(todo, quests_by_todo) for todo in saved_todos],
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


class TodoConfirmView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        serializer = TodoConfirmRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        items = serializer.validated_data["todos"]

        tag_ids = {item["tag_id"] for item in items if "tag_id" in item}
        tags_by_id = {
            tag.tag_id: tag for tag in Tag.objects.filter(user=user, tag_id__in=tag_ids)
        }
        missing_tag_ids = sorted(tag_ids - set(tags_by_id))
        if missing_tag_ids:
            return Response(
                {"error": {"tag_id": [f"존재하지 않는 태그입니다: {missing_tag_ids}"]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        saved_todos = [
            Todo.objects.create(
                user=user,
                tag=(
                    tags_by_id[item["tag_id"]]
                    if "tag_id" in item
                    else _ensure_tag(item.get("tags") or [], user)
                ),
                content=item["content"],
                todo_date=item["todo_date"],
            )
            for item in items
        ]
        quests_by_todo = _create_quest_drafts(user, saved_todos, items)
        if quests_by_todo:
            quest_triggered = True
        else:
            quests_by_todo, quest_triggered = _assign_quests_to_todos(user, saved_todos)

        todo_data = SavedTodoSerializer(
            [_serialize_saved_todo(todo, quests_by_todo) for todo in saved_todos],
            many=True,
        ).data
        return Response(
            {
                "todos": todo_data,
                "quest_distribution_triggered": quest_triggered,
            },
            status=status.HTTP_201_CREATED,
        )


class TodoQuestSyncView(APIView):
    """날짜가 바뀌어 todo_date 가 오늘이 된 TODO 에 뒤늦게 퀘스트를 채운다.

    미래 날짜로 만든 TODO(calendar_events 로 들어온 미래 일정 등)는 생성 시점엔
    퀘스트가 없다. _assign_quests_to_todos 가 "당일(todo_date == today)" TODO 에만
    부여하기 때문이다. 그 날이 되면 앱 진입 시 이 엔드포인트를 호출해, 오늘자이면서
    아직 퀘스트가 없는 진행 중 TODO 를 모아 기존 배정 로직에 그대로 넘긴다.
    하루 5개 한도/활성 캐릭터/AI 실패 graceful degrade 는 그 함수가 이미 보장하므로
    여기서 새 규칙을 만들지 않는다.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        user = request.user
        today = timezone.localdate()
        pending = list(
            Todo.objects.filter(
                user=user,
                todo_date=today,
                status=Todo.Status.IN_PROGRESS,
                quests__isnull=True,
            )
            .select_related("tag")
            .order_by("created_at")
        )
        quests_by_todo, quest_triggered = _assign_quests_to_todos(user, pending)

        todo_data = SavedTodoSerializer(
            [
                _serialize_saved_todo(todo, quests_by_todo)
                for todo in pending
                if str(todo.todo_id) in quests_by_todo
            ],
            many=True,
        ).data
        return Response(
            {
                "todos": todo_data,
                "quest_distribution_triggered": quest_triggered,
            },
            status=status.HTTP_200_OK,
        )


class TodoQuestPreviewView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        serializer = TodoQuestPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        items = serializer.validated_data["todos"]

        preview_todos = [
            {
                "todo_id": str(uuid.uuid4()),
                "content": item["content"],
                "tags": item.get("tags") or [],
            }
            for item in items
        ]
        active_characters = list(Character.objects.filter(user=user, is_active=True))
        remaining_daily_quota = len(preview_todos)
        generated = {"generated": []}
        if preview_todos and active_characters and remaining_daily_quota > 0:
            try:
                generated = _todo_ai_client().generate_quests(
                    todos=[{"todo_id": item["todo_id"]} for item in preview_todos],
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
            except TodoAIClientError as err:
                # AI 실패 시 가짜 퀘스트를 만들지 않고 빈 결과로 graceful degrade.
                logger.warning("quest preview AI 호출 실패: %s", err)
                generated = {"generated": []}

        characters_by_id = {
            str(character.character_id): character for character in active_characters
        }
        generated_by_todo = {
            str(item.get("todo_id", "")): item
            for item in generated.get("generated", [])
        }
        return Response(
            {
                "todos": [
                    {
                        "preview_id": item["todo_id"],
                        "content": item["content"],
                        "tags": item["tags"],
                        "quest": _serialize_preview_quest(
                            generated_by_todo.get(item["todo_id"]), characters_by_id
                        ),
                    }
                    for item in preview_todos
                ],
                "quest_distribution_triggered": bool(generated.get("generated")),
            },
            status=status.HTTP_200_OK,
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

        quest_ids = list(
            todo.quests.filter(status=Quest.Status.IN_PROGRESS).values_list(
                "quest_id", flat=True
            )
        )
        todo.quests.update(status=Quest.Status.COMPLETED, updated_at=timezone.now())

        def _schedule_feeds() -> None:
            from apps.posts.tasks import generate_feed_post

            for quest_id in quest_ids:
                try:
                    generate_feed_post.delay(str(quest_id))
                except Exception:
                    logger.warning("피드 생성 예약 실패: quest_id=%s", quest_id)

        transaction.on_commit(_schedule_feeds)

        if (
            not Todo.objects.filter(
                user=request.user,
                todo_date=todo.todo_date,
            )
            .exclude(status=Todo.Status.COMPLETED)
            .exists()
        ):
            create_reflection_notification(
                user=request.user,
                reflection_date=todo.todo_date,
            )

        return Response({"todo_id": str(todo.todo_id), "status": todo.status})


class TodoFailView(APIView):
    """사용자가 진행 중 TODO를 직접 실패(FAILED) 처리한다. 삭제하지 않음."""

    permission_classes = (IsAuthenticated,)

    def patch(self, request, todo_id) -> Response:
        todo = generics.get_object_or_404(Todo, todo_id=todo_id, user=request.user)
        if todo.status != Todo.Status.IN_PROGRESS:
            return Response(
                {"error": "포기할 수 없는 상태입니다."},
                status=status.HTTP_409_CONFLICT,
            )

        todo.status = Todo.Status.FAILED
        todo.save(update_fields=["status", "updated_at"])
        return Response({"todo_id": str(todo.todo_id), "status": todo.status})


class ScheduleCreateView(generics.CreateAPIView):
    serializer_class = ScheduleSerializer
    permission_classes = (IsAuthenticated,)

    def perform_create(self, serializer):
        tag = serializer.validated_data.get("tag") or _ensure_tag([], self.request.user)
        serializer.save(user=self.request.user, tag=tag)


class ScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ScheduleSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "schedule_id"

    def get_queryset(self):
        return Schedule.objects.filter(user=self.request.user).select_related("tag")


class CalendarMonthView(APIView):
    """캘린더 월 단위 조회: 해당 월에 걸치는 TODO와 일정을 함께 반환한다."""

    permission_classes = (IsAuthenticated,)

    def get(self, request) -> Response:
        try:
            year = int(request.query_params["year"])
            month = int(request.query_params["month"])
            first_day = date(year, month, 1)
            last_day = date(year, month, calendar_lib.monthrange(year, month)[1])
        except (KeyError, ValueError):
            return Response(
                {"error": "year, month 쿼리 파라미터가 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        todos = (
            Todo.objects.filter(
                user=request.user,
                todo_date__range=(first_day, last_day),
            )
            .select_related("tag")
            .order_by("todo_date")
        )
        # 시작일이 월말 이전이고, 종료일(없으면 시작일)이 월초 이후면 해당 월에 걸친다.
        schedules = (
            Schedule.objects.filter(
                Q(user=request.user)
                & Q(start_date__lte=last_day)
                & (
                    Q(end_date__gte=first_day)
                    | (Q(end_date__isnull=True) & Q(start_date__gte=first_day))
                )
            )
            .select_related("tag")
            .order_by("start_date")
        )

        return Response(
            {
                "todos": TodoSerializer(todos, many=True).data,
                "schedules": ScheduleSerializer(schedules, many=True).data,
            }
        )


def _todo_ai_client() -> TodoAIClient:
    return TodoAIClient(
        base_url=settings.MONGLE_AI_API_BASE,
        api_key=settings.MONGLE_AI_API_KEY,
        timeout_seconds=settings.MONGLE_AI_TIMEOUT_SECONDS,
    )


def _assign_quests_to_todos(
    user: User, saved_todos: list[Todo]
) -> tuple[dict[str, Quest], bool]:
    today = timezone.localdate()
    todays_todos = [todo for todo in saved_todos if todo.todo_date == today]
    active_characters = list(Character.objects.filter(user=user, is_active=True))
    if not todays_todos or not active_characters:
        return {}, False

    remaining_daily_quota = max(
        0,
        5 - Quest.objects.filter(todo__user=user, todo__todo_date=today).count(),
    )
    if remaining_daily_quota <= 0:
        return {}, False

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
    except TodoAIClientError as err:
        # AI 실패 시 가짜 퀘스트를 만들지 않는다. TODO 저장은 유지하고 퀘스트만 생략.
        logger.warning("quest 배정 AI 호출 실패: %s", err)
        return {}, False

    todos_by_id = {str(todo.todo_id): todo for todo in todays_todos}
    characters_by_id = {
        str(character.character_id): character for character in active_characters
    }
    quests_by_todo: dict[str, Quest] = {}
    for item in generated.get("generated", []):
        if len(quests_by_todo) >= remaining_daily_quota:
            break
        todo_id = str(item.get("todo_id", ""))
        character_id = str(item.get("character_id", ""))
        quest_text = item.get("quest_text")
        todo = todos_by_id.get(todo_id)
        character = characters_by_id.get(character_id)
        if todo is None or character is None or not quest_text:
            continue
        quest = Quest.objects.create(
            todo=todo,
            character=character,
            content=str(quest_text),
        )
        quests_by_todo[todo_id] = quest

    return quests_by_todo, bool(quests_by_todo)


def _serialize_preview_quest(
    item: dict[str, object] | None, characters_by_id: dict[str, Character]
) -> dict[str, object] | None:
    if item is None:
        return None
    character_id = str(item.get("character_id", ""))
    quest_text = item.get("quest_text")
    character = characters_by_id.get(character_id)
    if character is None or not quest_text:
        return None
    return {
        "content": str(quest_text),
        "character_id": character.character_id,
        "character_name": character.character_name,
        "character_image_url": character.gen_img_url,
    }


def _create_quest_drafts(
    user: User, saved_todos: list[Todo], items: list[dict[str, object]]
) -> dict[str, Quest]:
    characters_by_id = {
        str(character.character_id): character
        for character in Character.objects.filter(user=user, is_active=True)
    }
    quests_by_todo: dict[str, Quest] = {}
    for todo, item in zip(saved_todos, items, strict=False):
        draft = item.get("quest")
        if not isinstance(draft, dict):
            continue
        character = characters_by_id.get(str(draft.get("character_id", "")))
        content = draft.get("content")
        if character is None or not content:
            continue
        quest = Quest.objects.create(
            todo=todo,
            character=character,
            content=str(content),
        )
        quests_by_todo[str(todo.todo_id)] = quest
    return quests_by_todo


def _serialize_saved_todo(
    todo: Todo, quests_by_todo: dict[str, Quest]
) -> dict[str, object]:
    quest = quests_by_todo.get(str(todo.todo_id))
    return {
        "todo_id": todo.todo_id,
        "content": todo.content,
        "status": todo.status,
        "todo_date": todo.todo_date,
        "tags": [todo.tag.content],
        "quest": (
            {
                "quest_id": quest.quest_id,
                "content": quest.content,
                "character_id": quest.character_id,
                "character_name": quest.character.character_name,
            }
            if quest is not None
            else None
        ),
    }


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
