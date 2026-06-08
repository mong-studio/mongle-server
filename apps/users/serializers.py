from rest_framework import serializers  # DRF의 직렬화(JSON 변환) 도구

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    # 응답에서 유저 정보를 보여줄 때 사용하는 Serializer
    # 비밀번호 등 민감한 정보는 제외하고 필요한 필드만 포함

    class Meta:
        model = User
        fields = ("user_id", "email", "user_name", "token_balance", "created_at")
        read_only_fields = fields  # 이 Serializer는 읽기 전용 (수정 불가)
