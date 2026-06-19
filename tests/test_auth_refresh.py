"""POST /api/v1/auth/token/refresh 테스트 (AUTH-005)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.users.models import RefreshToken, User
from apps.users.refresh_token_service import (
    REFRESH_COOKIE_NAME,
    issue_refresh_token,
)
from apps.users.views import ACCESS_TOKEN_LIFETIME_SECONDS

REFRESH_URL = "/api/v1/auth/token/refresh"


def _client_with_cookie(raw_token: str) -> APIClient:
    client = APIClient()
    client.cookies[REFRESH_COOKIE_NAME] = raw_token
    return client


@pytest.mark.django_db
def test_refresh_success_rotates_token(user: User) -> None:
    """유효한 리프레시 쿠키로 요청하면
    200과 새 access_token을 반환하고 토큰이 회전된다.
    """
    raw_old, _ = issue_refresh_token(user)
    client = _client_with_cookie(raw_old)

    response = client.post(REFRESH_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_in_seconds"] == ACCESS_TOKEN_LIFETIME_SECONDS

    new_cookie = response.cookies[REFRESH_COOKIE_NAME].value
    assert new_cookie and new_cookie != raw_old
    assert RefreshToken.objects.filter(user=user).count() == 1

    # rotation: 이전 토큰으로 재요청하면 401
    retry = _client_with_cookie(raw_old).post(REFRESH_URL)
    assert retry.status_code == 401
    assert retry.json()["error"]["message"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.django_db
def test_refresh_persistent_token_keeps_persistent_cookie(user: User) -> None:
    """영구(자동로그인) 토큰을 재발급하면
    새 쿠키도 영구 쿠키여야 한다.
    """
    raw, _ = issue_refresh_token(user, persistent=True)
    response = _client_with_cookie(raw).post(REFRESH_URL)
    assert response.status_code == 200
    assert response.cookies[REFRESH_COOKIE_NAME]["max-age"]  # 영구 쿠키 유지


@pytest.mark.django_db
def test_refresh_session_token_keeps_short_lived_cookie(user: User) -> None:
    """세션 토큰을 재발급해도
    3시간 max_age 쿠키 성격을 유지해야 한다 (세션 만료 3시간 슬라이딩 + Safari ITP 대응).
    """
    raw, _ = issue_refresh_token(user, persistent=False)
    response = _client_with_cookie(raw).post(REFRESH_URL)
    assert response.status_code == 200
    # 세션 만료 3시간: 재발급(rotation) 시에도 3시간(10800초) 창을 유지(슬라이딩)
    assert response.cookies[REFRESH_COOKIE_NAME]["max-age"] == 10800


@pytest.mark.django_db
def test_refresh_without_cookie(db: None) -> None:
    """리프레시 쿠키 없이 요청하면
    401 INVALID_REFRESH_TOKEN을 반환한다.
    """
    response = APIClient().post(REFRESH_URL)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.django_db
def test_refresh_with_forged_token(db: None) -> None:
    """위조된 리프레시 토큰으로 요청하면
    401 INVALID_REFRESH_TOKEN을 반환한다.
    """
    response = _client_with_cookie("forged-token").post(REFRESH_URL)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.django_db
def test_refresh_expired_token_deletes_row(user: User) -> None:
    """만료된 리프레시 토큰으로 요청하면
    401 REFRESH_TOKEN_EXPIRED를 반환하고 해당 행을 삭제한다.
    """
    raw, _ = issue_refresh_token(user)
    RefreshToken.objects.filter(user=user).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    response = _client_with_cookie(raw).post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "REFRESH_TOKEN_EXPIRED"
    assert RefreshToken.objects.count() == 0


@pytest.mark.django_db
def test_refresh_inactive_user_deletes_row(user: User) -> None:
    """비활성화된 사용자의 리프레시 토큰으로 요청하면
    401을 반환하고 토큰 행을 삭제한다.
    """
    raw, _ = issue_refresh_token(user)
    User.objects.filter(pk=user.pk).update(is_active=False)

    response = _client_with_cookie(raw).post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_REFRESH_TOKEN"
    assert RefreshToken.objects.count() == 0


@pytest.mark.django_db
def test_refresh_concurrent_rotation_returns_401(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """행 검증은 통과하지만 rotation 직전 다른 요청이 먼저 소비해
    rotate_refresh_token이 None을 반환하는 경우 401을 반환한다."""
    raw, _ = issue_refresh_token(user)

    # 유효한 행이 존재해 validate는 통과하되,
    # rotate만 None을 반환하도록 강제
    monkeypatch.setattr("apps.users.views.rotate_refresh_token", lambda row: None)

    response = _client_with_cookie(raw).post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_REFRESH_TOKEN"
    # 새 토큰이 발급되지 않았음을 확인
    assert REFRESH_COOKIE_NAME not in response.cookies
