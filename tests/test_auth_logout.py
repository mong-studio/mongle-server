"""POST /api/v1/auth/logout 테스트 (AUTH-012)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.users.models import RefreshToken, User
from apps.users.refresh_token_service import (
    REFRESH_COOKIE_NAME,
    issue_refresh_token,
    validate_refresh_token,
)

LOGOUT_URL = "/api/v1/auth/logout"


# 로그아웃 시 현재 기기 토큰만 폐기되고 다른 기기 세션은 유지되는지 확인
@pytest.mark.django_db
def test_logout_revokes_only_current_token(auth_client: APIClient, user: User) -> None:
    raw_current, _ = issue_refresh_token(user, device_info="this-device")
    raw_other, _ = issue_refresh_token(user, device_info="other-device")
    auth_client.cookies[REFRESH_COOKIE_NAME] = raw_current

    response = auth_client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert validate_refresh_token(raw_current) is None
    assert validate_refresh_token(raw_other) is not None  # 다른 기기 세션 유지

    # 쿠키 만료 확인
    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value == ""


# refresh 쿠키 없이 로그아웃해도 204 반환 (멱등성 보장)
@pytest.mark.django_db
def test_logout_without_cookie_still_204(auth_client: APIClient) -> None:
    response = auth_client.post(LOGOUT_URL)
    assert response.status_code == 204
    assert RefreshToken.objects.count() == 0


# 비로그인 상태에서 로그아웃 요청 시 401 반환 확인
@pytest.mark.django_db
def test_logout_requires_access_token(db: None) -> None:
    response = APIClient().post(LOGOUT_URL)
    assert response.status_code == 401
