import re
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
        path = parsed.path.lstrip("/")
        # path-style: s3[.region].amazonaws.com/bucket/key → 첫 세그먼트가 버킷명
        if parsed.hostname.startswith("s3.") or parsed.hostname == "s3.amazonaws.com":
            _, _, path = path.partition("/")
        object_key = path
    else:
        object_key = raw

    if not object_key:
        return ""

    try:
        return generate_presigned_get_url(object_key)
    except StorageNotConfiguredError:
        return raw


# persona 는 "[성격]\n...[말투]\n...[배경]" 형식. [성격] 구획 본문만 캡처한다.
_PERSONALITY_RE = re.compile(r"\[성격\]\s*(.*?)(?=\[[^\]]+\]|$)", re.DOTALL)


def _extract_personality(persona: str) -> str:
    """persona 에서 [성격] 구획 본문만 추출한다(마커 없으면 원문 전체).

    프론트가 정규식으로 직접 자르지 않도록 서버에서 한 번만 파싱해 내려준다.
    """
    if not persona:
        return ""
    match = _PERSONALITY_RE.search(persona)
    return (match.group(1) if match else persona).strip()


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
    # 퀘스트 제목은 Quest 자신의 content (TODO 내용이 아니라 캐릭터에게 부여된 퀘스트).
    title = serializers.CharField(source="content", read_only=True)

    class Meta:
        model = Quest
        fields = ("quest_id", "todo_id", "title")
        read_only_fields = fields


class CharacterDetailSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)
    origin_img_url = serializers.SerializerMethodField()
    gen_img_url = serializers.SerializerMethodField()
    # persona 의 [성격] 구획만 추출한 값. 소개란에 그대로 쓴다.
    personality = serializers.SerializerMethodField()
    active_quests = serializers.SerializerMethodField()
    feed_count = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "origin_img_url",
            "gen_img_url",
            "persona",
            "personality",
            "is_active",
            "created_at",
            "active_quests",
            "feed_count",
        )
        read_only_fields = fields

    def get_personality(self, obj: Character) -> str:
        return _extract_personality(obj.persona)

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

    def get_feed_count(self, obj: Character) -> int:
        """캐릭터가 함께한 피드(Post) 수. posts 는 Post.character 의 related_name."""
        return obj.posts.count()


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
        min_length=0,
        max_length=3,
        required=False,
        default=list,
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
