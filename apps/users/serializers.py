from django.contrib.auth import authenticate
from rest_framework import serializers  # DRF의 직렬화(JSON 변환) 도구

from apps.users.models import User


class RegisterSerializer(serializers.ModelSerializer):
    # 회원가입 요청 데이터를 검증하고 User 객체를 생성하는 Serializer

    password = serializers.CharField(
        write_only=True,
        min_length=8,  # 8자 미만이면 자동으로 400 오류 반환
    )

    class Meta:
        model = User
        # 회원가입 시 받을 필드 목록
        fields = ["email", "password", "user_name", "job", "birth"]

    def create(self, validated_data):
        # is_valid() 통과 후 save() 호출 시 실행되는 메서드
        password = validated_data.pop(
            "password"
        )  # 딕셔너리에서 password를 꺼냄 (나머지 필드와 분리)
        user = User(**validated_data)  # password 제외한 나머지 필드로 User 객체 생성
        user.set_password(password)  # 비밀번호를 해시화해서 설정
        user.save()  # DB에 저장
        return user


class LoginSerializer(serializers.Serializer):
    # 로그인 요청을 검증하는 Serializer

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)  # 응답에 비밀번호 포함 안 함

    def validate(self, attrs):
        # is_valid() 호출 시 자동으로 실행되는 유효성 검사 메서드
        user = authenticate(email=attrs["email"], password=attrs["password"])
        # authenticate: 이메일+비밀번호가 맞으면 user 객체 반환, 틀리면 None 반환

        if not user:
            # 이메일이 없거나 비밀번호가 틀린 경우 — 보안상 어느 쪽인지 구분하지 않음
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        if not user.is_active:
            raise serializers.ValidationError("비활성화된 계정입니다.")

        attrs["user"] = user  # 검증된 user 객체를 다음 단계(View)로 전달
        return attrs


class UserSerializer(serializers.ModelSerializer):
    # 응답에서 유저 정보를 보여줄 때 사용하는 Serializer
    # 비밀번호 등 민감한 정보는 제외하고 필요한 필드만 포함

    class Meta:
        model = User
        fields = ["user_id", "email", "user_name", "token_balance", "created_at"]
        read_only_fields = fields  # 이 Serializer는 읽기 전용 (수정 불가)
