from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "user_id",
            "email",
            "user_name",
            "job",
            "birth",
            "token_balance",
            "created_at",
        )
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("user_name", "job", "birth")

    def validate_user_name(self, value: str) -> str:
        value = value.strip()
        if not (2 <= len(value) <= 8):
            raise serializers.ValidationError("닉네임은 2~8자여야 해요.")
        return value
