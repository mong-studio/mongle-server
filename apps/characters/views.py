from __future__ import annotations

from datetime import timedelta
import uuid

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.characters.models import (
    Character,
    CharacterGenerationJob,
    ImgGenLog,
    SourceImage,
)
from apps.characters.serializers import (
    CharacterDetailSerializer,
    CharacterListItemSerializer,
    CharacterRegisterSerializer,
    GenerationJobCreateSerializer,
    GenerationJobSerializer,
    SourceImageCreateSerializer,
)
from apps.characters.tasks import process_character_generation_job
from common.pagination import paginate_queryset

MAX_ACTIVE_CHARACTERS = 10
MAX_DAILY_GEN = 3
PRESIGNED_URL_EXPIRY_SECONDS = 600


class SourceImageCreateView(APIView):
    """CHAR-001: S3 presigned PUT URL 발급"""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        serializer = SourceImageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        file_name: str = data["file_name"]
        content_type: str = data["content_type"]
        content_length: int = data["content_length"]

        from infrastructure.storage.s3 import with_prefix

        ext_map = {"image/jpeg": "jpg", "image/png": "png"}
        ext = ext_map[content_type]
        object_key = with_prefix(
            f"source-images/{request.user.pk}/{uuid.uuid4()}.{ext}"  # type: ignore[union-attr]
        )
        _ = file_name

        expires_at = timezone.now() + timedelta(seconds=PRESIGNED_URL_EXPIRY_SECONDS)
        source_image = SourceImage.objects.create(
            user=request.user,
            object_key=object_key,
            content_type=content_type,
            status=SourceImage.Status.PENDING_UPLOAD,
            expires_at=expires_at,
        )

        from infrastructure.storage.s3 import (
            StorageNotConfiguredError,
            generate_presigned_put_url,
        )

        try:
            upload = generate_presigned_put_url(
                object_key=object_key,
                content_type=content_type,
                content_length=content_length,
                expiry=PRESIGNED_URL_EXPIRY_SECONDS,
            )
        except StorageNotConfiguredError:
            source_image.delete()
            return Response(
                {"error": "STORAGE_NOT_CONFIGURED"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "source_img_id": source_image.source_img_id,
                "object_key": object_key,
                "upload": upload,
                "expires_at": source_image.expires_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class GenerationJobCreateView(APIView):
    """CHAR-002: 캐릭터 AI 생성 Job 큐 등록"""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        serializer = GenerationJobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        user = request.user

        active_count = Character.objects.filter(user=user, is_active=True).count()
        if active_count >= MAX_ACTIVE_CHARACTERS:
            return Response(
                {"error": "CHARACTER_LIMIT_EXCEEDED"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        today_start = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(), timezone.datetime.min.time()
            )
        )
        daily_count = ImgGenLog.objects.filter(
            user=user, created_at__gte=today_start
        ).count()
        if daily_count >= MAX_DAILY_GEN:
            return Response(
                {"error": "DAILY_GENERATION_LIMIT_EXCEEDED"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        source_image = None
        source_img_id = data.get("source_img_id")
        if source_img_id:
            try:
                source_image = SourceImage.objects.get(
                    source_img_id=source_img_id, user=user
                )
            except SourceImage.DoesNotExist:
                return Response(
                    {"error": "SOURCE_IMAGE_NOT_FOUND"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                source_image.status == SourceImage.Status.UPLOAD_EXPIRED
                or timezone.now() > source_image.expires_at
            ):
                return Response(
                    {"error": "SOURCE_IMAGE_UPLOAD_EXPIRED"},
                    status=status.HTTP_410_GONE,
                )

            from infrastructure.storage.s3 import check_object_exists

            if check_object_exists(source_image.object_key):
                source_image.status = SourceImage.Status.UPLOAD_COMPLETED
                source_image.save(update_fields=["status"])

        job = CharacterGenerationJob.objects.create(
            user=user,
            source_image=source_image,
            personality_keywords=data["personality_keywords"],
            custom_prompt=data.get("custom_prompt", ""),
            status=CharacterGenerationJob.Status.QUEUED,
        )

        ImgGenLog.objects.create(user=user, gen_cnt=daily_count + 1)

        process_character_generation_job.delay(
            str(job.job_id), data["name"], data["persona"]
        )

        return Response(
            {
                "job_id": job.job_id,
                "status": job.status,
                "estimated_seconds": 60,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class GenerationJobDetailView(APIView):
    """CHAR-003: Job 상태 및 결과 조회"""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, job_id: uuid.UUID) -> Response:
        try:
            job = CharacterGenerationJob.objects.get(job_id=job_id, user=request.user)
        except CharacterGenerationJob.DoesNotExist:
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        serializer = GenerationJobSerializer(job)
        return Response(serializer.data)


class CharacterListView(APIView):
    """CHAR-004/005: 캐릭터 등록(POST) 및 목록 조회(GET)"""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        """CHAR-004: 성공한 Job으로 캐릭터 등록"""
        serializer = CharacterRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        user = request.user

        active_count = Character.objects.filter(user=user, is_active=True).count()
        if active_count >= MAX_ACTIVE_CHARACTERS:
            return Response(
                {"error": "CHARACTER_LIMIT_EXCEEDED"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            job = CharacterGenerationJob.objects.get(
                job_id=data["gen_job_id"], user=user
            )
        except CharacterGenerationJob.DoesNotExist:
            return Response(
                {"error": "JOB_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND
            )

        if job.status == CharacterGenerationJob.Status.CONSUMED:
            return Response(
                {"error": "JOB_ALREADY_CONSUMED"}, status=status.HTTP_409_CONFLICT
            )

        if job.status != CharacterGenerationJob.Status.SUCCEEDED:
            return Response(
                {"error": "JOB_NOT_SUCCEEDED"}, status=status.HTTP_400_BAD_REQUEST
            )

        character = Character.objects.create(
            user=user,
            generation_job=job,
            character_name=data["name"],
            gen_img_url=job.gen_img_url,
            persona=data["persona"],
            visual=job.appearance,
        )

        job.status = CharacterGenerationJob.Status.CONSUMED
        job.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "character_id": character.character_id,
                "name": character.character_name,
                "gen_img_url": character.gen_img_url,
                "persona": character.persona,
                "created_at": character.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit", 20))
        except (TypeError, ValueError):
            return Response(
                {"error": "INVALID_LIMIT"}, status=status.HTTP_400_BAD_REQUEST
            )
        if limit < 1 or limit > 100:
            return Response(
                {"error": "INVALID_LIMIT"}, status=status.HTTP_400_BAD_REQUEST
            )

        cursor = request.query_params.get("cursor")

        qs = Character.objects.filter(user=request.user, is_active=True).annotate(
            active_quest_count=Count(
                "quests",
                filter=Q(quests__todo__status="IN_PROGRESS"),
                distinct=True,
            )
        )
        try:
            items, next_cursor, has_next = paginate_queryset(
                qs, "character_id", limit, cursor
            )
        except ValueError:
            return Response(
                {"error": "INVALID_CURSOR"}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CharacterListItemSerializer(items, many=True)
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


class CharacterDetailView(APIView):
    """CHAR-006/007: 캐릭터 상세 조회(GET) 및 soft delete(DELETE)"""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, character_id: uuid.UUID) -> Response:
        try:
            character = Character.objects.get(
                character_id=character_id, user=request.user, is_active=True
            )
        except Character.DoesNotExist:
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CharacterDetailSerializer(character)
        return Response(serializer.data)

    def delete(self, request: Request, character_id: uuid.UUID) -> Response:
        """CHAR-007: 캐릭터 soft delete"""
        try:
            character = Character.objects.get(
                character_id=character_id, user=request.user, is_active=True
            )
        except Character.DoesNotExist:
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        active_count = Character.objects.filter(
            user=request.user, is_active=True
        ).count()
        if active_count <= 1:
            return Response(
                {"error": "LAST_CHARACTER"}, status=status.HTTP_409_CONFLICT
            )

        character.is_active = False
        character.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuestListView(APIView):
    """QUES-001: 캐릭터 퀘스트 목록 (cursor 페이지네이션)"""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, character_id: uuid.UUID) -> Response:
        try:
            character = Character.objects.get(
                character_id=character_id, user=request.user
            )
        except Character.DoesNotExist:
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        quest_status = request.query_params.get("status", "IN_PROGRESS")
        valid_statuses = {"IN_PROGRESS", "COMPLETED", "FAILED"}
        if quest_status not in valid_statuses:
            return Response(
                {"error": "INVALID_STATUS"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            limit = int(request.query_params.get("limit", 20))
        except (TypeError, ValueError):
            return Response(
                {"error": "INVALID_LIMIT"}, status=status.HTTP_400_BAD_REQUEST
            )
        if limit < 1 or limit > 100:
            return Response(
                {"error": "INVALID_LIMIT"}, status=status.HTTP_400_BAD_REQUEST
            )

        cursor = request.query_params.get("cursor")

        qs = character.quests.filter(status=quest_status).select_related("todo")
        try:
            items, next_cursor, has_next = paginate_queryset(
                qs, "quest_id", limit, cursor
            )
        except ValueError:
            return Response(
                {"error": "INVALID_CURSOR"}, status=status.HTTP_400_BAD_REQUEST
            )

        from apps.quests.serializers import QuestListItemSerializer

        serializer = QuestListItemSerializer(items, many=True)
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
