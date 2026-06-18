from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.http import HttpResponseBase
from django.utils import timezone
from rest_framework import status  # HTTP 상태코드 모음 (200, 201, 400 등)
from rest_framework.permissions import AllowAny, IsAuthenticated  # 접근 권한 클래스
from rest_framework.request import Request  # 타입 힌트용 Request 클래스
from rest_framework.response import Response  # JSON 응답을 만드는 클래스
from rest_framework.views import APIView  # DRF의 기본 View 클래스
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken  # JWT 토큰 생성 도구

from apps.users.api_errors import error_response, validation_error_response
from apps.users.models import RefreshToken as RefreshTokenRow, User
from apps.users.rate_limit import client_ip, hit_rate_limit
from apps.users.refresh_token_service import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    set_refresh_cookie,
    validate_refresh_token,
)
from apps.users.serializers import UserSerializer, UserUpdateSerializer
from apps.users.validators import (
    collect_validated_fields,
    validate_email,
    validate_password,
    validate_required_boolean,
)

ACCESS_TOKEN_LIFETIME_SECONDS = int(jwt_settings.ACCESS_TOKEN_LIFETIME.total_seconds())

# 로그인 brute-force 방어: 동일 IP에서 윈도우당 허용 시도 횟수.
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60


def _login_user_payload(user: User) -> dict[str, object]:
    return {
        "user_id": str(user.user_id),
        "email": user.email,
        "user_name": user.user_name,
        "has_character": user.characters.exists(),
    }


# 로그인
class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> HttpResponseBase:
        # 검증/인증 이전에 IP 단위로 시도 횟수를 제한해 brute-force를 막는다.
        if hit_rate_limit(
            f"login:{client_ip(request)}",
            limit=LOGIN_RATE_LIMIT,
            window_seconds=LOGIN_RATE_WINDOW_SECONDS,
        ):
            response = error_response(429, "LOGIN_RATE_LIMITED")
            response["Retry-After"] = str(LOGIN_RATE_WINDOW_SECONDS)
            return response

        try:
            payload = self._validate_payload(request)
        except ValidationError as exc:
            return validation_error_response(exc)

        user = authenticate(
            request, email=payload["email"], password=payload["password"]
        )
        # authenticate는 비밀번호 불일치·미존재·비활성 모두 None을 반환
        # 계정 존재 여부를 노출하지 않기 위해 모두 동일한 에러 사용
        if user is None:
            return error_response(401, "INVALID_CREDENTIALS")

        access_token = AccessToken.for_user(user)
        response = Response(
            {
                "access_token": str(access_token),
                "token_type": "Bearer",
                "expires_in_seconds": ACCESS_TOKEN_LIFETIME_SECONDS,
                "users": _login_user_payload(user),
            }
        )

        # 자동로그인(remember_me)이면 영구 쿠키, 아니면 세션 쿠키로 항상 발급한다.
        # 세션 쿠키도 새로고침에는 유지되므로 로그인이 즉시 풀리지 않음
        remember_me = bool(payload["remember_me"])
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        raw_token, _ = issue_refresh_token(
            user, device_info=user_agent, persistent=remember_me
        )
        set_refresh_cookie(response, raw_token, persistent=remember_me)

        return response

    @staticmethod
    def _validate_payload(request: Request) -> dict[str, object]:
        """필드별 검증 에러를 모아 한 번에 반환"""
        if not isinstance(request.data, dict):
            raise ValidationError({"body": ["JSON object를 입력해 주세요."]})
        validators: tuple[tuple[str, object], ...] = (
            ("email", lambda: validate_email(request.data.get("email"))),
            ("password", lambda: validate_password(request.data.get("password"))),
            (
                "remember_me",
                lambda: validate_required_boolean(
                    request.data.get("remember_me"), "remember_me"
                ),
            ),
        )
        return collect_validated_fields(validators)  # type: ignore[arg-type]


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return validation_error_response(ValidationError(serializer.errors))
        serializer.save()
        return Response(UserSerializer(request.user).data)


class RefreshView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> HttpResponseBase:
        raw_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not raw_token:
            return error_response(401, "INVALID_REFRESH_TOKEN")

        row = validate_refresh_token(raw_token)
        if row is None:
            return error_response(401, "INVALID_REFRESH_TOKEN")

        if row.expires_at <= timezone.now():
            RefreshTokenRow.objects.filter(pk=row.pk).delete()
            return error_response(401, "REFRESH_TOKEN_EXPIRED")

        if not row.user.is_active:
            RefreshTokenRow.objects.filter(pk=row.pk).delete()
            return error_response(401, "INVALID_REFRESH_TOKEN")

        user = row.user
        persistent = row.persistent  # 회전 후에도 세션/영구 성격을 유지하려고 미리 보관
        rotated = rotate_refresh_token(row)
        if rotated is None:
            # 동시 요청이 먼저 rotate함 — 재사용 시도로 간주
            return error_response(401, "INVALID_REFRESH_TOKEN")
        new_raw_token, _ = rotated
        access_token = AccessToken.for_user(user)

        response = Response(
            {
                "access_token": str(access_token),
                "expires_in_seconds": ACCESS_TOKEN_LIFETIME_SECONDS,
            }
        )
        set_refresh_cookie(response, new_raw_token, persistent=persistent)
        return response


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> HttpResponseBase:
        raw_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if raw_token:
            revoke_refresh_token(raw_token)

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> HttpResponseBase:
        if not isinstance(request.data, dict):
            return error_response(400, "VALIDATION_ERROR")

        current_password = request.data.get("current_password")
        new_password_raw = request.data.get("new_password")

        if not isinstance(current_password, str) or not current_password:
            return validation_error_response(
                ValidationError(
                    {"current_password": ["현재 비밀번호를 입력해 주세요."]}
                )
            )

        if not request.user.check_password(current_password):  # type: ignore[union-attr]
            return error_response(400, "INVALID_CURRENT_PASSWORD")

        try:
            validated_new = validate_password(new_password_raw)
        except ValidationError as exc:
            return validation_error_response(exc)

        request.user.set_password(validated_new)  # type: ignore[union-attr]
        request.user.save(update_fields=["password"])  # type: ignore[union-attr]

        return Response(status=status.HTTP_204_NO_CONTENT)
