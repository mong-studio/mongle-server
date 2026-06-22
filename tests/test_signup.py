from __future__ import annotations

import json
from typing import Any

from django.core import mail
from django.test import Client, override_settings
from django.utils import timezone
import fakeredis
import pytest

from apps.users import signup_views as account_views
from apps.users.models import User

pytestmark = pytest.mark.django_db


def post_json(client: Client, path: str, payload: dict[str, Any]) -> Any:
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def fake_redis_store(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    """
    Redis 연결을 fakeredis로 교체하는 픽스처.

    signup_views가 세션 대신 Redis를 사용하도록 변경되었기 때문에
    테스트에서도 실제 Redis 대신 인메모리 fakeredis를 사용한다.
    autouse=True 로 이 파일의 모든 테스트에 자동 적용된다.
    """
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(account_views, "_get_redis", lambda: fake)
    return fake


# 이메일 인증 요청 시 Redis에 상태 저장 및 인증 코드가 포함된 이메일 발송 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_request_stores_state_and_sends_code(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()

    response = post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "USER@example.com", "purpose": "SIGNUP"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "expires_in_seconds": 180,
        "resend_available_in_seconds": 30,
    }
    assert mail.outbox[0].to == ["user@example.com"]
    assert "ABCDEF" in mail.outbox[0].body

    # 세션 대신 Redis에 저장됐는지 확인
    raw = fake_redis_store.get("email_verification:user@example.com:SIGNUP")
    assert raw is not None
    verification = json.loads(raw)
    assert verification["email"] == "user@example.com"
    assert verification["purpose"] == "SIGNUP"


# 이미 가입된 이메일로 인증 요청 시 409 EMAIL_DUPLICATED 반환 확인
def test_email_verification_request_rejects_duplicated_email() -> None:
    User.objects.create_user(
        email="user@example.com",
        password="password123!",
        user_name="몽글이",
        birth="2000-01-01",
    )
    client = Client()

    response = post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "EMAIL_DUPLICATED"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_verification_sends_code_to_active_email_user(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    User.objects.create_user(
        email="user@example.com",
        password="password123!",
        user_name="몽글이",
        birth="2000-01-01",
    )
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")

    response = post_json(
        Client(),
        "/api/v1/auth/email-verification",
        {"email": "USER@example.com", "purpose": "PASSWORD_RESET"},
    )

    assert response.status_code == 201
    assert mail.outbox[0].to == ["user@example.com"]
    assert "ABCDEF" in mail.outbox[0].body
    assert (
        fake_redis_store.get("email_verification:user@example.com:PASSWORD_RESET")
        is not None
    )


@pytest.mark.parametrize(
    "email,is_active",
    [
        ("unknown@example.com", None),
        ("inactive@example.com", False),
    ],
)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_verification_rejects_unavailable_email_without_sending(
    email: str,
    is_active: bool | None,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    if is_active is not None:
        User.objects.create_user(
            email=email,
            password="password123!",
            user_name="몽글이",
            birth="2000-01-01",
            is_active=is_active,
        )

    response = post_json(
        Client(),
        "/api/v1/auth/email-verification",
        {"email": email, "purpose": "PASSWORD_RESET"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": 404,
        "message": "USER_NOT_FOUND",
        "details": {},
    }
    assert mail.outbox == []
    assert fake_redis_store.get(f"email_verification:{email}:PASSWORD_RESET") is None


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_verification_rejects_social_user_without_sending(
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    User.objects.create_user(
        email="social@example.com",
        user_name="소셜유저",
        birth="2000-01-01",
        login_type=User.LoginType.KAKAO,
    )

    response = post_json(
        Client(),
        "/api/v1/auth/email-verification",
        {"email": "social@example.com", "purpose": "PASSWORD_RESET"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "SOCIAL_ACCOUNT_NO_PASSWORD"
    assert mail.outbox == []
    assert (
        fake_redis_store.get("email_verification:social@example.com:PASSWORD_RESET")
        is None
    )


# 30초 이내 동일 이메일로 재발송 요청 시 429 EMAIL_VERIFICATION_RATE_LIMITED 반환 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_request_rate_limits_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    payload = {"email": "user@example.com", "purpose": "SIGNUP"}

    first_response = post_json(client, "/api/v1/auth/email-verification", payload)
    second_response = post_json(client, "/api/v1/auth/email-verification", payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert (
        second_response.json()["error"]["message"] == "EMAIL_VERIFICATION_RATE_LIMITED"
    )


# 올바른 인증 코드 확인 시 verified=true 및 verification_token 발급 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_marks_email_verified(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    response = post_json(
        client,
        "/api/v1/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    # confirm 완료 후 verification_token이 발급되는지 확인
    assert "verification_token" in body
    assert body["verification_token"]

    # email 기반 키는 삭제되고 token 기반 키가 생성됐는지 확인
    assert fake_redis_store.get("email_verification:user@example.com:SIGNUP") is None
    token_key = f"email_verified:{body['verification_token']}"
    assert fake_redis_store.get(token_key) is not None


# 잘못된 인증 코드로 확인 요청 시 400 INVALID_VERIFICATION_CODE 반환 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_rejects_invalid_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    response = post_json(
        client,
        "/api/v1/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ZZZZZZ"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "INVALID_VERIFICATION_CODE"


# 만료된 인증 코드로 확인 요청 시 400 VERIFICATION_CODE_EXPIRED 반환 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_rejects_expired_code(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    # Redis에 저장된 인증 상태의 만료 시간을 과거로 변경
    raw = fake_redis_store.get("email_verification:user@example.com:SIGNUP")
    assert raw is not None
    verification = json.loads(raw)
    verification["expires_at"] = (
        timezone.now() - timezone.timedelta(seconds=1)
    ).isoformat()
    fake_redis_store.set(
        "email_verification:user@example.com:SIGNUP", json.dumps(verification)
    )

    response = post_json(
        client,
        "/api/v1/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "VERIFICATION_CODE_EXPIRED"


# 이메일 인증 완료 후 회원가입 성공 시 유저 생성 및 verification_token 삭제 확인
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_signup_creates_user_and_clears_verification_state(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_store: fakeredis.FakeRedis,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/api/v1/auth/email-verification",
        {"email": "USER@example.com", "purpose": "SIGNUP"},
    )
    confirm_response = post_json(
        client,
        "/api/v1/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )
    verification_token = confirm_response.json()["verification_token"]

    response = post_json(
        client,
        "/api/v1/auth/signup",
        {
            "email": "USER@example.com",
            "password": "password123!",
            "user_name": "몽글이",
            "job": "사무직",
            "birth": "1999-07-22",
            "is_aiconsent": False,
            "verification_token": verification_token,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["user_name"] == "몽글이"
    assert body["token_balance"] == 5
    user = User.objects.get(email="user@example.com")
    assert user.check_password("password123!")
    assert user.job == "사무직"
    assert user.birth.isoformat() == "1999-07-22"
    assert user.is_aiconsent is False

    # 회원가입 완료 후 verification_token 삭제 확인
    assert fake_redis_store.get(f"email_verified:{verification_token}") is None


# 이메일 인증 없이 회원가입 시도 시 400 EMAIL_NOT_VERIFIED 반환 확인
def test_signup_rejects_unverified_email() -> None:
    client = Client()

    response = post_json(
        client,
        "/api/v1/auth/signup",
        {
            "email": "user@example.com",
            "password": "password123!",
            "user_name": "몽글이",
            "birth": "1999-07-22",
            "is_aiconsent": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "EMAIL_NOT_VERIFIED"


# 비밀번호·닉네임 유효성 검사 실패 시 400과 필드별 오류 반환 확인
def test_signup_validates_password_and_user_name() -> None:
    client = Client()

    response = post_json(
        client,
        "/api/v1/auth/signup",
        {
            "email": "user@example.com",
            "password": "password",
            "user_name": "몽 글",
            "is_aiconsent": True,
        },
    )

    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert "password" in details
    assert "user_name" in details
