"""비밀번호 변경 시 자동로그인 토큰 무효화 테스트 (AUTH 스펙).

스펙: "사용자가 비밀번호를 변경하거나 로그아웃한 경우, 기존 기기의 자동 로그인 토큰을 무효화한다."
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.users.models import RefreshToken, User
from apps.users.refresh_token_service import (
    REFRESH_COOKIE_NAME,
    issue_refresh_token,
    revoke_all_user_tokens,
)

CHANGE_PASSWORD_URL = "/api/v1/auth/change-password/"  # noqa: S105  # URL, not a secret


@pytest.mark.django_db
def test_revoke_all_user_tokens_deletes_every_row(user: User) -> None:
    """revoke_all_user_tokens는 유저의 모든 refresh token 행을 삭제한다."""
    issue_refresh_token(user, persistent=True)
    issue_refresh_token(user, persistent=False)
    assert RefreshToken.objects.filter(user=user).count() == 2

    deleted = revoke_all_user_tokens(user)

    assert deleted == 2
    assert RefreshToken.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_change_password_revokes_other_devices_keeps_current(
    auth_client: APIClient, user: User
) -> None:
    """비밀번호 변경 시 모든 기기 토큰을 폐기하고,
    현재 기기에는 새 토큰을 재발급해 로그인을 유지한다."""
    # 다른 기기 2대 + 현재 기기 1대
    issue_refresh_token(user, device_info="other-1", persistent=True)
    issue_refresh_token(user, device_info="other-2", persistent=True)
    current_raw, _ = issue_refresh_token(user, device_info="current", persistent=False)
    auth_client.cookies[REFRESH_COOKIE_NAME] = current_raw

    response = auth_client.post(
        CHANGE_PASSWORD_URL,
        {"current_password": "password123", "new_password": "newpassword456"},
        format="json",
    )

    assert response.status_code == 204
    # 기존 3개 토큰은 모두 폐기되고, 현재 기기용 새 토큰 1개만 남는다.
    assert RefreshToken.objects.filter(user=user).count() == 1
    # 현재 기기는 새 쿠키를 받아 로그인이 유지된다.
    assert response.cookies[REFRESH_COOKIE_NAME].value
    # 비밀번호가 실제로 변경됐다.
    user.refresh_from_db()
    assert user.check_password("newpassword456")
