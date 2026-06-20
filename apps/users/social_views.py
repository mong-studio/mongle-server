"""카카오 소셜 로그인/회원가입 뷰."""

from __future__ import annotations

import json
import secrets
from typing import Any

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBase
import redis as redis_lib
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.api_errors import error_response
from apps.users.models import SocialAccount, User
from apps.users.views import build_login_response
from infrastructure.kakao import (
    KakaoError,
    KakaoProfile,
    exchange_code_for_token,
    fetch_kakao_profile,
)

SOCIAL_SIGNUP_TTL_SECONDS = 600
_PROVIDER = "kakao"


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _signup_key(token: str) -> str:
    return f"social_signup:{token}"


def save_social_signup_token(email: str, provider_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _redis().set(
        _signup_key(token),
        json.dumps({"email": email, "provider_id": provider_id, "provider": _PROVIDER}),
        ex=SOCIAL_SIGNUP_TTL_SECONDS,
    )
    return token


def load_social_signup_token(token: str) -> dict[str, Any] | None:
    raw = _redis().get(_signup_key(token))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


def delete_social_signup_token(token: str) -> None:
    _redis().delete(_signup_key(token))


def _login_existing(user: User, profile: KakaoProfile, request: Request) -> Response:
    """기존 유저(소셜 or 이메일)에 카카오를 연동(필요 시)하고 로그인 응답을 만든다."""
    SocialAccount.objects.get_or_create(
        provider=_PROVIDER,
        provider_id=profile.provider_id,
        defaults={"user": user},
    )
    return build_login_response(
        user, request, persistent=True, extra={"status": "authenticated"}
    )


class KakaoLoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> HttpResponseBase:
        code = request.data.get("code") if isinstance(request.data, dict) else None
        if not isinstance(code, str) or not code:
            return error_response(
                400, "VALIDATION_ERROR", {"code": ["코드가 필요해요."]}
            )

        try:
            access_token = exchange_code_for_token(code)
            profile = fetch_kakao_profile(access_token)
        except KakaoError:
            return error_response(502, "SOCIAL_LOGIN_FAILED")

        social = (
            SocialAccount.objects.select_related("user")
            .filter(provider=_PROVIDER, provider_id=profile.provider_id)
            .first()
        )
        if social is not None:
            return _login_existing(social.user, profile, request)

        if not profile.email:
            return error_response(409, "EMAIL_REQUIRED")

        existing = User.objects.filter(email=profile.email).first()
        if existing is not None:
            with transaction.atomic():
                return _login_existing(existing, profile, request)

        signup_token = save_social_signup_token(profile.email, profile.provider_id)
        return Response(
            {
                "status": "profile_required",
                "signup_token": signup_token,
                "email": profile.email,
            }
        )
