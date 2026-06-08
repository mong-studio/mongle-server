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

REFRESH_TOKEN_LIFETIME = timedelta(weeks=2)
REFRESH_COOKIE_NAME = "mongle_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_refresh_token(
    user: User, device_info: str = "", persistent: bool = True
) -> tuple[str, datetime]:
    """무작위 토큰 생성, DB에는 해시만 저장. (원본, 만료시각) 반환.

    persistent=False면 세션 로그인용 토큰으로 표시한다(쿠키도 세션 쿠키로 내려감).
    """
    raw_token = secrets.token_urlsafe(48)
    expires_at = timezone.now() + REFRESH_TOKEN_LIFETIME
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
    # persistent=True면 만료시각 있는 영구 쿠키,
    # False면 세션 쿠키(브라우저 닫으면 만료).
    max_age = int(REFRESH_TOKEN_LIFETIME.total_seconds()) if persistent else None
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: HttpResponse) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
