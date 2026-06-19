from urllib.parse import urlparse

from rest_framework import serializers

from apps.characters.models import Character, CharacterGenerationJob, SourceImage
from apps.quests.models import Quest
from apps.todos.models import Todo


def _resolve_gen_img_url(raw: str) -> str:
    """gen_img_url 컬럼이 S3 presigned URL이면 object key를 추출해 새로 서명해 반환한다.

    presigned URL 만료 문제를 해결하기 위해 origin_img_url과 동일한 패턴을 적용한다.
    S3 URL(.amazonaws.com)이 아니면 원본값을 그대로 반환한다.
    """
    if not raw:
        return ""

    from infrastructure.storage.s3 import (
        StorageNotConfiguredError,
        generate_presigned_get_url,
    )

    parsed = urlparse(raw)

    if parsed.scheme in ("http", "https"):
        if not parsed.hostname or not parsed.hostname.endswith(".amazonaws.com"):
            return raw
        object_key = parsed.path.lstrip("/")
    else:
        object_key = raw

    if not object_key:
        return ""

    try:
        return generate_presigned_get_url(object_key)
    except StorageNotConfiguredError:
        return raw


class CharacterListItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)
    active_quest_count = serializers.IntegerField(read_only=True)
    gen_img_url = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "gen_img_url",
            "active_quest_count",
        )
        read_only_fields = fields

    def get_gen_img_url(self, obj: Character) -> str:
        return _resolve_gen_img_url(obj.gen_img_url)


class ActiveQuestSerializer(serializers.ModelSerializer):
    todo_id = serializers.UUIDField(source="todo.todo_id", read_only=True)
    title = serializers.CharField(source="todo.content", read_only=True)

    class Meta:
        model = Quest
        fields = ("quest_id", "todo_id", "title")
        read_only_fields = fields


class CharacterDetailSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)
    origin_img_url = serializers.SerializerMethodField()
    gen_img_url = serializers.SerializerMethodField()
    active_quests = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "origin_img_url",
            "gen_img_url",
            "persona",
            "is_active",
            "created_at",
            "active_quests",
        )
        read_only_fields = fields

    def get_gen_img_url(self, obj: Character) -> str:
        return _resolve_gen_img_url(obj.gen_img_url)

    def get_origin_img_url(self, obj: Character) -> str:
        """origin_img_url 컬럼엔 원본 사진의 S3 object_key 가 들어있다.

        비공개 객체라 조회 시점에 presigned GET URL 로 서명해 반환한다. 매번 새로
        서명하므로 만료 걱정이 없다. 사진 없이 생성했거나 S3 미설정이면 빈 문자열.
        """
        object_key = obj.origin_img_url
        if not object_key:
            return ""

        from infrastructure.storage.s3 import (
            StorageNotConfiguredError,
            generate_presigned_get_url,
        )

        try:
            return generate_presigned_get_url(object_key)
        except StorageNotConfiguredError:
            return ""

    def get_active_quests(self, obj: Character) -> list[dict[str, object]]:
        active_quests = (
            obj.quests.select_related("todo")
            .filter(todo__status=Todo.Status.IN_PROGRESS)
            .order_by("-created_at")
        )
        return ActiveQuestSerializer(active_quests, many=True).data


class CharacterRegisterSerializer(serializers.Serializer):
    gen_job_id = serializers.UUIDField()
    name = serializers.CharField(max_length=8)
    # persona 는 등록 시 받지 않는다. AI 가 생성해 job.persona 에 저장된 정제본을 쓴다.


class SourceImageCreateSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=["image/jpeg", "image/png"])
    content_length = serializers.IntegerField(min_value=1, max_value=5 * 1024 * 1024)


class GenerationJobCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=8)
    persona = serializers.CharField()
    source_img_id = serializers.UUIDField(required=False, allow_null=True)
    personality_keywords = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=1,
        max_length=3,
    )
    custom_prompt = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )


class GenerationJobSerializer(serializers.ModelSerializer):
    result = serializers.SerializerMethodField()

    class Meta:
        model = CharacterGenerationJob
        fields = ("job_id", "status", "result", "created_at", "updated_at")

    def get_result(self, obj: CharacterGenerationJob) -> dict | None:
        if obj.status == CharacterGenerationJob.Status.SUCCEEDED:
            return {
                "gen_img_url": _resolve_gen_img_url(obj.gen_img_url),
                "persona": obj.persona,
            }
        return None


class SourceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceImage
        fields = ("source_img_id", "object_key", "expires_at")
