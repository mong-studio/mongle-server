from rest_framework import serializers

from apps.characters.models import Character


class CharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = [
            "character_id",
            "character_name",
            "gen_img_url",
            "description",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["character_id", "created_at"]
