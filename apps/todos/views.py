"""TODO list/detail + AI bridge views."""

from __future__ import annotations

import logging
from secrets import compare_digest
import uuid

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
    TodoConfirmRequestSerializer,
    TodoGenerateRequestSerializer,
    TodoQuestPreviewRequestSerializer,
)
from apps.users.models import User
from apps.users.notification_service import create_reflection_notification

logger = logging.getLogger(__name__)


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
        serializer.save(user=self.request.user)


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
        except TodoAIClientError:
            # TODO: AI 서버 연결이 안정화되면 이 테스트용 fallback을 제거하고
            # 아래 에러 응답을 되살리기.
            # return Response({"error": str(err)}, status=status.HTTP_502_BAD_GATEWAY)
            result = _build_fallback_todo_candidates(
                serializer.validated_data["prompt"],
                today,
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


class TodoCommitAIView(APIView):
    permission_classes = (InternalServiceTokenPermission,)

    def post(self, request) -> Response:
        serializer = TodoCommitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _resolve_user(request)
        return _save_todo_candidates(user, serializer.validated_data)


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
            except TodoAIClientError:
                # TODO: AI 서버 연결이 안정화되면 이 preview fallback을 제거하고
                # generated = {"generated": []} 로 되돌리기.
                generated = _build_fallback_preview_quests(
                    preview_todos,
                    active_characters,
                    remaining_daily_quota,
                )

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
    except TodoAIClientError:
        return _build_fallback_quests_for_todos(
            todays_todos,
            active_characters,
            remaining_daily_quota,
        )

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


def _build_fallback_todo_candidates(prompt: str, today: str) -> dict[str, object]:
    separators = ("그리고", "하고", "및", ",", ".", "\n", "·")
    parts = [prompt]
    for separator in separators:
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(part.split(separator))
        parts = next_parts

    titles = [part.strip()[:20] for part in parts if len(part.strip()) > 1]
    if not titles:
        titles = [prompt.strip()[:20] or "오늘 할 일"]

    return {
        "kind": "candidates",
        "thread_id": str(uuid.uuid4()),
        "todos": [
            {
                "title": title,
                "due_date": today,
                "tags": [_guess_fallback_todo_tag(title)],
            }
            for title in titles[:6]
        ],
        "calendar_events": [],
        "summary_text": "AI 서버 연결 전이라 임시로 TODO를 나눴어요.",
    }


def _guess_fallback_todo_tag(title: str) -> str:
    if any(keyword in title for keyword in ("운동", "헬스", "병원", "약", "스트레칭")):
        return "건강"
    if any(keyword in title for keyword in ("청소", "빨래", "설거지", "정리")):
        return "집안일"
    if any(keyword in title for keyword in ("공부", "강의", "책", "마이그레이션")):
        return "공부"
    if any(keyword in title for keyword in ("업무", "회의", "기획서", "작업")):
        return "작업"
    return "일상"


def _build_fallback_preview_quests(
    preview_todos: list[dict[str, object]],
    characters: list[Character],
    remaining_daily_quota: int,
) -> dict[str, list[dict[str, object]]]:
    # TODO: AI 서버 연결이 안정화되면 이 preview fallback 생성 로직을 제거하기.
    generated: list[dict[str, object]] = []
    if remaining_daily_quota <= 0:
        return {"generated": generated}

    for index, item in enumerate(preview_todos[:remaining_daily_quota]):
        character = characters[index % len(characters)]
        generated.append(
            {
                "todo_id": item["todo_id"],
                "character_id": str(character.character_id),
                "quest_text": _fallback_quest_content(character, index),
            }
        )
    return {"generated": generated}


def _build_fallback_quests_for_todos(
    todos: list[Todo], characters: list[Character], remaining_daily_quota: int
) -> tuple[dict[str, Quest], bool]:
    # TODO: AI 서버 연결이 안정화되면 이 fallback 생성 로직을 제거하고
    # TodoAIClientError 발생 시 기존처럼 ({}, False)를 반환하도록 되돌리기.
    quests_by_todo: dict[str, Quest] = {}
    if remaining_daily_quota <= 0:
        return quests_by_todo, False

    for index, todo in enumerate(todos[:remaining_daily_quota]):
        character = characters[index % len(characters)]
        quest = Quest.objects.create(
            todo=todo,
            character=character,
            content=_fallback_quest_content(character, index),
        )
        quests_by_todo[str(todo.todo_id)] = quest

    return quests_by_todo, bool(quests_by_todo)


def _fallback_quest_content(character: Character, index: int) -> str:
    persona = (character.persona or "").lower()
    if any(keyword in persona for keyword in ("활발", "밝", "장난", "에너지")):
        return f"{character.character_name}가 햇살 길에서 폴짝 산책하기"
    if any(keyword in persona for keyword in ("차분", "조용", "느긋", "사색")):
        return f"{character.character_name}가 작은 찻잔 옆에서 구름 일기 쓰기"
    if any(keyword in persona for keyword in ("꼼꼼", "성실", "정리", "계획")):
        return f"{character.character_name}가 반짝 단추를 색깔별로 정리하기"
    if any(keyword in persona for keyword in ("상냥", "다정", "친절", "따뜻")):
        return f"{character.character_name}가 마을 꽃들에게 안부 인사하기"
    if any(keyword in persona for keyword in ("호기심", "탐험", "궁금", "모험")):
        return f"{character.character_name}가 숨은 별조각 세 개 찾아보기"

    fallback_activities = [
        "몽글 구름에 리본 달아주기",
        "작은 꽃밭에 반짝 물방울 뿌리기",
        "포근한 방석 위에서 낮잠 자리 고르기",
        "마을 우체통에 응원 편지 넣기",
        "조약돌에게 귀여운 이름 붙여주기",
    ]
    activity = fallback_activities[index % len(fallback_activities)]
    return f"{character.character_name}가 {activity}"


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
