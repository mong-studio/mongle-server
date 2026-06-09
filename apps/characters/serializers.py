from rest_framework import serializers

from apps.characters.models import Character, CharacterGenerationJob, SourceImage


class CharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = (
            "character_id",
            "character_name",
            "gen_img_url",
            "persona",
            "is_active",
            "created_at",
        )
        read_only_fields = ("character_id", "created_at")


class CharacterListItemSerializer(serializers.ModelSerializer):
    active_quest_count = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = ("character_id", "character_name", "gen_img_url", "active_quest_count")

    def get_active_quest_count(self, obj: Character) -> int:
        return obj.quests.filter(status="IN_PROGRESS").count()


class CharacterDetailSerializer(serializers.ModelSerializer):
    active_quests = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = (
            "character_id",
            "character_name",
            "gen_img_url",
            "persona",
            "active_quests",
        )

    def get_active_quests(self, obj: Character) -> list:
        from apps.quests.serializers import QuestListItemSerializer

        qs = obj.quests.filter(status="IN_PROGRESS").select_related("todo")
        return QuestListItemSerializer(qs, many=True).data


class CharacterRegisterSerializer(serializers.Serializer):
    gen_job_id = serializers.UUIDField()
    name = serializers.CharField(max_length=50)
    persona = serializers.CharField()


class SourceImageCreateSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=["image/jpeg", "image/png"])
    content_length = serializers.IntegerField(min_value=1, max_value=5 * 1024 * 1024)


class GenerationJobCreateSerializer(serializers.Serializer):
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
            return {"gen_img_url": obj.gen_img_url, "persona": obj.persona}
        return None


class SourceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceImage
        fields = ("source_img_id", "object_key", "expires_at")
