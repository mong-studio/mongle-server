"""Users 앱 테스트 - 회원가입, 로그인, 내 정보"""

from __future__ import annotations

from datetime import timedelta

from django.test import Client
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.users.models import User


def _make_verified_client(email: str) -> Client:
    """이메일 인증 세션이 완료된 Django 테스트 클라이언트를 반환합니다."""
    client = Client()
    session = client.session
    session["email_verification"] = {
        "email": email,
        "purpose": "SIGNUP",
        "verified_until": (timezone.now() + timedelta(minutes=10)).isoformat(),
    }
    session.save()
    return client


@pytest.mark.django_db
def test_register_success() -> None:
    client = _make_verified_client("new@test.com")
    response = client.post(
        "/auth/signup",
        {
            "email": "new@test.com",
            "password": "password123!",
            "user_name": "신규유저",
            "is_aiconsent": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_register_duplicate_email(user: User) -> None:
    client = _make_verified_client("test@test.com")
    response = client.post(
        "/auth/signup",
        {
            "email": "test@test.com",
            "password": "password123!",
            "user_name": "중복",
            "is_aiconsent": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_register_short_password() -> None:
    client = APIClient()
    response = client.post(
        "/auth/signup",
        {"email": "short@test.com", "password": "1234", "user_name": "짧은비번"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login_success(user: User) -> None:
    client = APIClient()
    response = client.post(
        "/auth/login",
        {"email": "test@test.com", "password": "password123"},
        format="json",
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.django_db
def test_login_wrong_password(user: User) -> None:
    client = APIClient()
    response = client.post(
        "/auth/login",
        {"email": "test@test.com", "password": "wrongpassword"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_login_nonexistent_email() -> None:
    client = APIClient()
    response = client.post(
        "/auth/login",
        {"email": "nobody@test.com", "password": "password123"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_me_authenticated(auth_client: APIClient, user: User) -> None:
    response = auth_client.get("/auth/me/")
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"


@pytest.mark.django_db
def test_me_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/auth/me/")
    assert response.status_code == 401
