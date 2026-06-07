"""Users 앱 테스트 - 회원가입, 로그인, 내 정보"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.users.models import User


@pytest.mark.django_db
def test_register_success() -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"email": "new@test.com", "password": "password123", "user_name": "신규유저"},
        format="json",
    )
    assert response.status_code == 201
    assert "access" in response.json()
    assert "refresh" in response.json()


@pytest.mark.django_db
def test_register_duplicate_email(user: User) -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"email": "test@test.com", "password": "password123", "user_name": "중복"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_register_short_password() -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"email": "short@test.com", "password": "1234", "user_name": "짧은비번"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login_success(user: User) -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "test@test.com", "password": "password123"},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()


@pytest.mark.django_db
def test_login_wrong_password(user: User) -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "test@test.com", "password": "wrongpassword"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login_nonexistent_email() -> None:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@test.com", "password": "password123"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_me_authenticated(auth_client: APIClient, user: User) -> None:
    response = auth_client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"


@pytest.mark.django_db
def test_me_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 401
