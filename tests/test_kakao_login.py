from datetime import date
from unittest.mock import patch

import fakeredis
import httpx
import pytest
from rest_framework.test import APIClient

from apps.users import social_views
from apps.users.models import SocialAccount, User
from apps.users.serializers import UserSerializer
from infrastructure import kakao
from infrastructure.kakao import KakaoProfile


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


# ---------------------------------------------------------------------------
# KakaoLoginView tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_redis_kakao(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    """social_views._redis()를 fakeredis로 교체한다."""
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(social_views, "_redis", lambda: fake)
    return fake


def _patch_kakao(email: str | None) -> "patch":  # type: ignore[type-arg]
    return patch.multiple(
        social_views,
        exchange_code_for_token=lambda code: "tok",
        fetch_kakao_profile=lambda tok: KakaoProfile(provider_id="kid-1", email=email),
    )


@pytest.mark.django_db
def test_kakao_login_new_user_returns_profile_required() -> None:
    with _patch_kakao("new@example.com"):
        res = APIClient().post(
            "/api/v1/auth/social/kakao", {"code": "c"}, format="json"
        )
    assert res.status_code == 200
    assert res.json()["status"] == "profile_required"
    assert res.json()["email"] == "new@example.com"
    assert res.json()["signup_token"]


@pytest.mark.django_db
def test_kakao_login_links_existing_email_user() -> None:
    User.objects.create_user(
        email="dup@example.com",
        password="Passw0rd!",
        user_name="기존",
        birth=date(1990, 5, 5),
    )
    with _patch_kakao("dup@example.com"):
        res = APIClient().post(
            "/api/v1/auth/social/kakao", {"code": "c"}, format="json"
        )
    assert res.status_code == 200
    assert res.json()["status"] == "authenticated"
    assert SocialAccount.objects.filter(provider="kakao", provider_id="kid-1").exists()


@pytest.mark.django_db
def test_kakao_login_existing_social_logs_in() -> None:
    user = User.objects.create_user(
        email="s@example.com",
        user_name="소셜",
        birth=date(1995, 1, 1),
        login_type=User.LoginType.KAKAO,
    )
    SocialAccount.objects.create(user=user, provider="kakao", provider_id="kid-1")
    with _patch_kakao("s@example.com"):
        res = APIClient().post(
            "/api/v1/auth/social/kakao", {"code": "c"}, format="json"
        )
    assert res.status_code == 200
    assert res.json()["status"] == "authenticated"
    assert res.json()["users"]["email"] == "s@example.com"


@pytest.mark.django_db
def test_kakao_login_requires_email() -> None:
    with _patch_kakao(None):
        res = APIClient().post(
            "/api/v1/auth/social/kakao", {"code": "c"}, format="json"
        )
    assert res.status_code == 409
    assert res.json()["error"]["message"] == "EMAIL_REQUIRED"
