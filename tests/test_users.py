"""Users 앱의 내 정보 조회 API 동작을 검증합니다."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.users.models import User


@pytest.mark.django_db
def test_me_authenticated(auth_client: APIClient, user: User) -> None:
    # 로그인한 사용자는 내 정보 조회 API에서 자신의 이메일을 받을 수 있습니다.
    response = auth_client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"


@pytest.mark.django_db
def test_me_unauthenticated() -> None:
    # 로그인하지 않은 사용자는 내 정보 조회 API에 접근할 수 없습니다.
    client = APIClient()
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 401
