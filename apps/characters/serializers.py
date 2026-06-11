from rest_framework import serializers

from apps.characters.models import Character, CharacterGenerationJob, SourceImage
from apps.quests.models import Quest
from apps.todos.models import Todo


class CharacterListItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)
    active_quest_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "gen_img_url",
            "active_quest_count",
        )
        read_only_fields = fields


class ActiveQuestSerializer(serializers.ModelSerializer):
    todo_id = serializers.UUIDField(source="todo.todo_id", read_only=True)
    title = serializers.CharField(source="todo.content", read_only=True)

    class Meta:
        model = Quest
        fields = ("quest_id", "todo_id", "title")
        read_only_fields = fields


class CharacterDetailSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)
    active_quests = serializers.SerializerMethodField()

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "gen_img_url",
            "persona",
            "is_active",
            "created_at",
            "active_quests",
        )
        read_only_fields = fields

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
