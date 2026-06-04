from __future__ import annotations

import json
from typing import Any

from django.core import mail
from django.test import Client, override_settings
from django.utils import timezone
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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_request_stores_session_and_sends_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()

    response = post_json(
        client,
        "/auth/email-verification",
        {"email": "USER@example.com", "purpose": "SIGNUP"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "expires_in_seconds": 180,
        "resend_available_in_seconds": 30,
    }
    assert mail.outbox[0].to == ["user@example.com"]
    assert "ABCDEF" in mail.outbox[0].body
    verification = client.session["email_verification"]
    assert verification["email"] == "user@example.com"
    assert verification["purpose"] == "SIGNUP"


def test_email_verification_request_rejects_duplicated_email() -> None:
    User.objects.create_user(
        email="user@example.com",
        password="password123!",
        user_name="몽글이",
    )
    client = Client()

    response = post_json(
        client,
        "/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "EMAIL_DUPLICATED"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_request_rate_limits_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    payload = {"email": "user@example.com", "purpose": "SIGNUP"}

    first_response = post_json(client, "/auth/email-verification", payload)
    second_response = post_json(client, "/auth/email-verification", payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert (
        second_response.json()["error"]["message"] == "EMAIL_VERIFICATION_RATE_LIMITED"
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_marks_email_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    response = post_json(
        client,
        "/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is True
    verification = client.session["email_verification"]
    assert verification["verified_until"] is not None
    assert "code_hash" not in verification


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_rejects_invalid_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )

    response = post_json(
        client,
        "/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ZZZZZZ"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "INVALID_VERIFICATION_CODE"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_verification_confirm_rejects_expired_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/auth/email-verification",
        {"email": "user@example.com", "purpose": "SIGNUP"},
    )
    session = client.session
    verification = session["email_verification"]
    verification["expires_at"] = (
        timezone.now() - timezone.timedelta(seconds=1)
    ).isoformat()
    session["email_verification"] = verification
    session.save()

    response = post_json(
        client,
        "/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "VERIFICATION_CODE_EXPIRED"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_signup_creates_user_and_clears_verification_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_views, "_generate_code", lambda: "ABCDEF")
    client = Client()
    post_json(
        client,
        "/auth/email-verification",
        {"email": "USER@example.com", "purpose": "SIGNUP"},
    )
    post_json(
        client,
        "/auth/email-verification/confirm",
        {"email": "user@example.com", "purpose": "SIGNUP", "code": "ABCDEF"},
    )

    response = post_json(
        client,
        "/auth/signup",
        {
            "email": "USER@example.com",
            "password": "password123!",
            "user_name": "몽글이",
            "job": "사무직",
            "birth": "1999-07-22",
            "is_aiconsent": False,
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
    assert "email_verification" not in client.session


def test_signup_rejects_unverified_email() -> None:
    client = Client()

    response = post_json(
        client,
        "/auth/signup",
        {
            "email": "user@example.com",
            "password": "password123!",
            "user_name": "몽글이",
            "is_aiconsent": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "EMAIL_NOT_VERIFIED"


def test_signup_validates_password_and_user_name() -> None:
    client = Client()

    response = post_json(
        client,
        "/auth/signup",
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
