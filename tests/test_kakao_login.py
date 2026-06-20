from datetime import date

import httpx
import pytest

from apps.users.models import User
from apps.users.serializers import UserSerializer
from infrastructure import kakao


@pytest.mark.django_db
def test_user_serializer_includes_login_type():
    user = User.objects.create_user(
        email="a@example.com",
        password="Passw0rd!",
        user_name="민지",
        birth=date(2000, 1, 1),
    )
    data = UserSerializer(user).data
    assert data["login_type"] == "email"
    assert "login_type" in data


def test_fetch_kakao_profile_parses_id_and_email(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(
            200,
            json={"id": 12345, "kakao_account": {"email": "k@example.com"}},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(kakao.httpx, "get", fake_get)
    profile = kakao.fetch_kakao_profile("dummy-token")
    assert profile.provider_id == "12345"
    assert profile.email == "k@example.com"


def test_fetch_kakao_profile_missing_email_returns_none(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(
            200,
            json={"id": 999, "kakao_account": {}},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(kakao.httpx, "get", fake_get)
    profile = kakao.fetch_kakao_profile("dummy-token")
    assert profile.provider_id == "999"
    assert profile.email is None
