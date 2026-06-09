import base64
import binascii
from datetime import datetime
import uuid

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import (
    generics,  # CRUD를 자동으로 처리해주는 DRF 제네릭 View
    status,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from apps.characters.ai_client import CharacterAIClient, CharacterAIClientError
from apps.characters.models import Character
from apps.characters.serializers import (
    CharacterDetailSerializer,
    CharacterGenerateRequestSerializer,
    CharacterListItemSerializer,
    CharacterSerializer,
)
from apps.todos.models import Todo

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_ACTIVE_CHARACTERS = 10


def encode_cursor(created_at: datetime, character_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{character_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_raw, character_id_raw = decoded.split("|", maxsplit=1)
        created_at = datetime.fromisoformat(created_at_raw)
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(
                created_at, timezone.get_current_timezone()
            )
        return created_at, uuid.UUID(character_id_raw)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValidationError({"cursor": "유효하지 않은 cursor 입니다."}) from exc


class CharacterListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)  # 로그인한 사람만 접근 가능

    def get_queryset(self):
        # "내 캐릭터 중 활성화된 것만 조회"
        # 다른 유저의 캐릭터는 절대 반환되지 않음
        return (
            Character.objects.filter(user=self.request.user, is_active=True)
            .annotate(
                active_quest_count=Count(
                    "quests",
                    filter=Q(quests__todo__status=Todo.Status.IN_PROGRESS),
                    distinct=True,
                )
            )
            .order_by("-created_at", "-character_id")
        )

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CharacterListItemSerializer
        return CharacterSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        try:
            requested_limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"limit": "limit 는 1 이상의 숫자여야 합니다."}
            ) from exc

        limit = min(max(requested_limit, 1), MAX_LIMIT)
        cursor = request.query_params.get("cursor")

        if cursor:
            created_at, character_id = decode_cursor(cursor)
            queryset = queryset.filter(
                Q(created_at__lt=created_at)
                | Q(created_at=created_at, character_id__lt=character_id)
            )

        items = list(queryset[: limit + 1])
        has_next = len(items) > limit
        page_items = items[:limit]

        next_cursor = None
        if has_next and page_items:
            last_item = page_items[-1]
            next_cursor = encode_cursor(last_item.created_at, last_item.character_id)

        serializer = self.get_serializer(page_items, many=True)
        return Response(
            {
                "items": serializer.data,
                "page": {
                    "limit": limit,
                    "next_cursor": next_cursor,
                    "has_next": has_next,
                },
            }
        )

    def perform_create(self, serializer):
        # 캐릭터 생성 시 user 필드를 현재 로그인한 유저로 자동 설정
        # 앱에서 user_id를 직접 보내지 않아도 됨 (보안상 서버에서 설정)
        serializer.save(user=self.request.user)


class CharacterDetailView(generics.RetrieveUpdateDestroyAPIView):
    # RetrieveUpdateDestroyAPIView: 조회/수정/삭제를 한 클래스에서 모두 처리

    permission_classes = (IsAuthenticated,)
    lookup_field = "character_id"  # URL의 {character_id} 값으로 DB에서 캐릭터를 찾음

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CharacterDetailSerializer
        return CharacterSerializer

    def get_queryset(self):
        # 내 캐릭터만 수정/삭제 가능 (다른 유저의 캐릭터는 404 반환)
        return Character.objects.filter(user=self.request.user).prefetch_related(
            "quests__todo"
        )


class CharacterGenerateAIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request) -> Response:
        active_count = Character.objects.filter(
            user=request.user,
            is_active=True,
        ).count()
        if active_count >= MAX_ACTIVE_CHARACTERS:
            return Response(
                {"error": "캐릭터는 최대 10명까지 생성할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CharacterGenerateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        source_image_url = data.get("source_image_url") or None

        try:
            result = _character_ai_client().create(
                user_id=str(request.user.user_id),
                name=data["name"],
                persona=data["persona"],
                personality_keywords=data.get("personality_keywords", []),
                source_image_url=source_image_url,
            )
        except CharacterAIClientError as err:
            return Response({"error": str(err)}, status=status.HTTP_502_BAD_GATEWAY)

        character = Character.objects.create(
            user=request.user,
            character_name=result.get("name") or data["name"],
            origin_img_url=_safe_model_url(source_image_url),
            gen_img_url=result.get("image_url") or "",
            persona=result.get("persona") or data["persona"],
        )
        return Response(
            {
                "character_id": str(character.character_id),
                "name": character.character_name,
                "persona": character.persona,
                "personality": result.get("personality", ""),
                "speech_style": result.get("speech_style", ""),
                "background": result.get("background", ""),
                "image_url": character.gen_img_url,
                "source_image_url": source_image_url,
            },
            status=status.HTTP_201_CREATED,
        )


def _character_ai_client() -> CharacterAIClient:
    return CharacterAIClient(
        base_url=settings.MONGLE_AI_API_BASE,
        api_key=settings.MONGLE_AI_API_KEY,
        timeout_seconds=settings.MONGLE_AI_TIMEOUT_SECONDS,
    )


def _safe_model_url(value: str | None) -> str:
    if not value or len(value) > 500:
        return ""
    return value
