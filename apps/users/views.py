import hashlib

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import RefreshToken as RefreshTokenModel
from apps.users.serializers import LoginSerializer, RegisterSerializer, UserSerializer


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    # 기본 설정은 "로그인한 사람만 접근 가능"이지만
    # 회원가입은 로그인 전에 하는 것이므로 누구나 접근 가능하도록 변경

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        # request.data: 앱이 보낸 JSON 데이터 (email, password, user_name 등)
        # RegisterSerializer에 데이터를 넘겨서 유효성 검사 준비

        serializer.is_valid(raise_exception=True)
        # 유효성 검사 실행

        user = serializer.save()
        # 검증 통과 후 RegisterSerializer의 create() 메서드 호출 → DB에 유저 저장

        refresh = RefreshToken.for_user(user)
        # 새로 만든 유저의 JWT 토큰 발급
        # refresh: 2주짜리 refresh 토큰
        # refresh.access_token: 1시간짜리 access 토큰

        return Response(
            {
                "user": UserSerializer(user).data,  # 유저 정보 JSON
                "access": str(refresh.access_token),  # 이후 API 요청에 사용할 토큰
                "refresh": str(refresh),  # 토큰 갱신에 사용할 토큰
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)  # 로그인도 당연히 누구나 접근 가능

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            # 400 VALIDATION_ERROR: 입력값 오류 (이메일 형식 틀림, 필드 누락 등)
            if "email" in serializer.errors or "password" in serializer.errors:
                return Response(
                    {
                        "error": {
                            "code": 400,
                            "message": "VALIDATION_ERROR",
                            "details": serializer.errors,
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # 401 INVALID_CREDENTIALS: 이메일/비밀번호 불일치
            return Response(
                {"error": {"code": 401, "message": "INVALID_CREDENTIALS"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)  # 해당 유저의 JWT 토큰 발급
        remember_me = serializer.validated_data.get("remember_me", False)

        response = Response(
            {
                "access_token": str(refresh.access_token),
                "token_type": "bearer",
                "expires_in_seconds": 3600,
                "users": {
                    "user_id": str(user.user_id),
                    "email": user.email,
                    "user_name": user.user_name,
                    "has_character": False,
                },
            }
        )

        if remember_me:
            # refresh token을 해시화해서 DB에 저장
            # 원본 토큰이 아닌 해시값만 저장해서 탈취되더라도 안전
            token_str = str(refresh)
            token_hash = hashlib.sha256(token_str.encode()).hexdigest()
            RefreshTokenModel.objects.create(
                user=user,
                token_hash=token_hash,
                # HTTP_USER_AGENT: 어떤 기기에서 로그인했는지
                device_info=request.META.get("HTTP_USER_AGENT", ""),
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )

            # remember_me=true 시 refresh token을 HttpOnly cookie로 발급
            response.set_cookie(
                key="refresh_token",
                value=token_str,
                httponly=True,
                # 개발환경(DEBUG=True)에서는 False, 배포환경에서는 True
                secure=not settings.DEBUG,
                samesite="Lax",
                max_age=7 * 24 * 60 * 60,  # 7일
            )

        return response


class TokenRefreshView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            # 401 INVALID_REFRESH_TOKEN: 인증되지 않은 token
            return Response(
                {"error": {"code": 401, "message": "INVALID_REFRESH_TOKEN"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            refresh = RefreshToken(refresh_token)
            # HttpOnly cookie에서 refresh token을 읽어 새 access token 발급
            return Response(
                {
                    "access_token": str(refresh.access_token),
                    "expires_in_seconds": 3600,
                }
            )
        except TokenError:
            # 401 REFRESH_TOKEN_EXPIRED: refresh token 만료
            return Response(
                {"error": {"code": 401, "message": "REFRESH_TOKEN_EXPIRED"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class MeView(APIView):
    permission_classes = (IsAuthenticated,)
    # 로그인한 사람만 접근 가능 (JWT 토큰 필요)

    def get(self, request: Request) -> Response:
        # request.user: JWT 토큰에서 자동으로 추출한 현재 로그인 유저 객체
        return Response(UserSerializer(request.user).data)
