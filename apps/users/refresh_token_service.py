"""Opaque refresh token 발급/검증/rotation/폐기 + 쿠키 헬퍼."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from apps.users.models import RefreshToken, User

# persistent=True (자동로그인): 2주 / persistent=False (세션 로그인): 1일
# Safari ITP는 Max-Age 없는 세션 쿠키를 XHR 응답에서 신뢰하지 않으므로 항상 명시한다.
REFRESH_TOKEN_LIFETIME_PERSISTENT = timedelta(weeks=2)
REFRESH_TOKEN_LIFETIME_SESSION = timedelta(days=1)
REFRESH_COOKIE_NAME = "mongle_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_refresh_token(
    user: User, device_info: str = "", persistent: bool = True
) -> tuple[str, datetime]:
    """무작위 토큰 생성, DB에는 해시만 저장. (원본, 만료시각) 반환.

    persistent=True(자동로그인): 2주 / False(세션 로그인): 1일.
    """
    raw_token = secrets.token_urlsafe(48)
    lifetime = (
        REFRESH_TOKEN_LIFETIME_PERSISTENT
        if persistent
        else REFRESH_TOKEN_LIFETIME_SESSION
    )
    expires_at = timezone.now() + lifetime
    RefreshToken.objects.create(
        user=user,
        token_hash=_hash_token(raw_token),
        device_info=device_info[:255],
        expires_at=expires_at,
        persistent=persistent,
    )
    return raw_token, expires_at


def validate_refresh_token(raw_token: str) -> RefreshToken | None:
    """해시로 행 조회. 없으면 None. (만료 검사는 호출자 책임)"""
    try:
        return RefreshToken.objects.select_related("user").get(
            token_hash=_hash_token(raw_token),
        )
    except RefreshToken.DoesNotExist:
        return None


def rotate_refresh_token(row: RefreshToken) -> tuple[str, datetime] | None:
    """기존 행 폐기 후 user/device_info를 승계한 새 토큰 발급 (원자적).

    이미 다른 요청이 행을 삭제했다면(동시 rotation/replay) None을 반환한다.
    """
    with transaction.atomic():
        deleted, _ = RefreshToken.objects.filter(pk=row.pk).delete()
        if deleted == 0:
            return None
        return issue_refresh_token(row.user, row.device_info, persistent=row.persistent)


def revoke_refresh_token(raw_token: str) -> None:
    """해당 토큰 행만 삭제. 없으면 무시."""
    RefreshToken.objects.filter(token_hash=_hash_token(raw_token)).delete()


def set_refresh_cookie(
    response: HttpResponse, raw_token: str, persistent: bool = True
) -> None:
    # 항상 max_age를 명시한다.
    # Safari ITP는 XHR Set-Cookie 세션 쿠키를 새로고침 후 드롭할 수 있어
    # persistent 여부와 무관하게 만료를 지정한다.
    lifetime = (
        REFRESH_TOKEN_LIFETIME_PERSISTENT
        if persistent
        else REFRESH_TOKEN_LIFETIME_SESSION
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        raw_token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: HttpResponse) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
