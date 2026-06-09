from rest_framework import serializers

from apps.characters.models import Character
from apps.quests.models import Quest
from apps.todos.models import Todo


class CharacterGenerateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    persona = serializers.CharField()
    personality_keywords = serializers.ListField(
        child=serializers.CharField(),
        max_length=3,
        required=False,
        allow_empty=True,
    )
    source_image_url = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )


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


class CharacterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="character_name", read_only=True)

    class Meta:
        model = Character
        fields = (
            "character_id",
            "name",
            "gen_img_url",
            "persona",
            "is_active",
            "created_at",
        )
        read_only_fields = ("character_id", "created_at")
