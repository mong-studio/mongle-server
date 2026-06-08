"""POST /api/v1/auth/login 테스트 (AUTH-004)."""

from __future__ import annotations

import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.characters.models import Character
from apps.users.models import RefreshToken, User
from apps.users.refresh_token_service import REFRESH_COOKIE_NAME

LOGIN_URL = "/api/v1/auth/login"


def _login(client: APIClient, **overrides: object) -> Response:
    payload: dict[str, object] = {
        "email": "test@test.com",
        "password": "password123",
        "remember_me": False,
    }
    payload.update(overrides)
    return client.post(LOGIN_URL, payload, format="json")


@pytest.mark.django_db
def test_login_success_response_shape(user: User) -> None:
    """유효한 자격증명으로 로그인하면
    200과 access_token·token_type·expires_in_seconds·users를 반환한다.
    """
    response = _login(APIClient())
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "Bearer"  # noqa: S105
    assert body["expires_in_seconds"] == 3600
    assert body["users"] == {
        "user_id": str(user.user_id),
        "email": "test@test.com",
        "user_name": "테스터",
        "has_character": False,
    }


@pytest.mark.django_db
def test_login_has_character_true(user: User, character: Character) -> None:
    """캐릭터가 있는 사용자가 로그인하면 응답의 has_character가 true다."""
    response = _login(APIClient())
    assert response.json()["users"]["has_character"] is True


@pytest.mark.django_db
def test_login_remember_me_sets_persistent_cookie(user: User) -> None:
    """자동로그인 ON이면 만료시각 있는 영구 refresh 쿠키를 발급한다."""
    response = _login(APIClient(), remember_me=True)
    assert response.status_code == 200

    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["samesite"] == "Lax"
    # remember_me=true → 만료시각이 있는 영구 쿠키
    assert cookie["max-age"]
    row = RefreshToken.objects.get(user=user)
    assert row.persistent is True


@pytest.mark.django_db
def test_login_without_remember_me_sets_session_cookie(user: User) -> None:
    """자동로그인 OFF면 세션 쿠키(새로고침 유지, 브라우저 닫으면 만료)를 발급한다."""
    response = _login(APIClient(), remember_me=False)
    assert response.status_code == 200

    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["path"] == "/api/v1/auth"
    # remember_me=false → 만료시각 없는 세션 쿠키(새로고침은 유지, 브라우저 닫으면 만료)
    assert cookie["max-age"] == ""
    assert cookie["expires"] == ""
    row = RefreshToken.objects.get(user=user)
    assert row.persistent is False


@pytest.mark.django_db
def test_login_wrong_password_is_invalid_credentials(user: User) -> None:
    """잘못된 비밀번호로 로그인하면 401 INVALID_CREDENTIALS를 반환한다."""
    response = _login(APIClient(), password="wrongpass1")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_login_unknown_email_same_error(db: None) -> None:
    """존재하지 않는 이메일로 로그인하면 401 INVALID_CREDENTIALS를 반환한다."""
    response = _login(APIClient(), email="nobody@test.com")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_login_inactive_user_same_error(db: None) -> None:
    """비활성화된 계정으로 로그인하면 401 INVALID_CREDENTIALS를 반환한다."""
    User.objects.create_user(
        email="inactive@test.com",
        password="password123",
        user_name="비활성",
        is_active=False,
    )
    response = _login(APIClient(), email="inactive@test.com")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_login_validation_error(db: None) -> None:
    """잘못된 형식의 이메일·짧은 비밀번호로 요청하면
    400 VALIDATION_ERROR와 필드별 오류를 반환한다.
    """
    response = _login(APIClient(), email="not-an-email", password="short")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["message"] == "VALIDATION_ERROR"
    assert "email" in body["error"]["details"]
    assert "password" in body["error"]["details"]


@pytest.mark.django_db
def test_login_remember_me_must_be_boolean(user: User) -> None:
    """remember_me에 불리언이 아닌 값을 보내면 400 VALIDATION_ERROR를 반환한다."""
    response = _login(APIClient(), remember_me="yes")
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_login_non_dict_body_returns_400(db: None) -> None:
    """딕셔너리가 아닌 JSON 배열로 요청하면 400 VALIDATION_ERROR를 반환한다."""
    client = APIClient()
    response = client.post(LOGIN_URL, [1, 2], format="json")
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_login_missing_remember_me_is_validation_error(user: User) -> None:
    """remember_me 필드를 누락하면 400 VALIDATION_ERROR를 반환한다."""
    client = APIClient()
    response = client.post(
        LOGIN_URL,
        {"email": "test@test.com", "password": "password123"},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_login_rate_limited_after_threshold(user: User) -> None:
    """동일 IP에서 임계치를 넘는 로그인 시도는 429로 차단된다 (brute-force 방어)."""
    from apps.users.views import LOGIN_RATE_LIMIT

    client = APIClient()
    # 임계치까지는 인증 실패(401)이지 차단(429)은 아니다.
    for _ in range(LOGIN_RATE_LIMIT):
        resp = _login(client, password="wrongpass1")
        assert resp.status_code == 401

    # 임계치 초과 → 429
    blocked = _login(client, password="wrongpass1")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["message"] == "LOGIN_RATE_LIMITED"
    assert blocked["Retry-After"]


@pytest.mark.django_db
def test_login_rate_limit_blocks_even_correct_credentials(user: User) -> None:
    """차단 상태에서는 올바른 자격증명도 429로 막혀 자격증명 확인을 막는다."""
    from apps.users.views import LOGIN_RATE_LIMIT

    client = APIClient()
    for _ in range(LOGIN_RATE_LIMIT + 1):
        _login(client, password="wrongpass1")

    resp = _login(client)  # 올바른 비밀번호
    assert resp.status_code == 429
