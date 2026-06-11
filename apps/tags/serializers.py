from rest_framework import serializers

from apps.tags.models import Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("tag_id", "content", "color")
        read_only_fields = ("tag_id",)
