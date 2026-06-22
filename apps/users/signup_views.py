"""Email-verification and signup API views."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import json
import secrets
import string
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import redis as redis_lib

from apps.users.api_errors import error_response, validation_error_response
from apps.users.models import User
from apps.users.refresh_token_service import revoke_all_user_tokens
from apps.users.validators import (
    collect_validated_fields,
    parse_json_body,
    validate_birth,
    validate_email,
    validate_optional_string,
    validate_password,
    validate_purpose,
    validate_required_boolean,
    validate_user_name,
    validate_verification_code,
)

VERIFICATION_EXPIRES_SECONDS = 180
VERIFICATION_RESEND_SECONDS = 30
VERIFICATION_VERIFIED_SECONDS = 600
VERIFICATION_MAX_ATTEMPTS = 5


def _get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _redis_key(email: str, purpose: str) -> str:
    return f"email_verification:{email}:{purpose}"


def _get_verification(email: str, purpose: str) -> dict[str, Any] | None:
    raw = _get_redis().get(_redis_key(email, purpose))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


def _save_verification(
    email: str, purpose: str, data: dict[str, Any], ttl: int
) -> None:
    _get_redis().set(_redis_key(email, purpose), json.dumps(data), ex=ttl)


def _delete_verification(email: str, purpose: str) -> None:
    _get_redis().delete(_redis_key(email, purpose))


def _verified_token_key(token: str) -> str:
    return f"email_verified:{token}"


def _save_verified_token(token: str, email: str, purpose: str) -> None:
    _get_redis().set(
        _verified_token_key(token),
        json.dumps({"email": email, "purpose": purpose}),
        ex=VERIFICATION_VERIFIED_SECONDS,
    )


def _get_verified_token(token: str) -> dict[str, Any] | None:
    raw = _get_redis().get(_verified_token_key(token))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


def _delete_verified_token(token: str) -> None:
    _get_redis().delete(_verified_token_key(token))


def _hash_code(code: str) -> str:
    return salted_hmac(
        "email-verification-code",
        code,
        secret=settings.SECRET_KEY,
    ).hexdigest()


def _generate_code() -> str:
    alphabet = string.ascii_uppercase
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _isoformat(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@csrf_exempt
@require_POST
def request_email_verification(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        email = validate_email(body.get("email"))
        purpose = validate_purpose(body.get("purpose"))
    except ValidationError as exc:
        return validation_error_response(exc)

    if purpose == "SIGNUP" and User.objects.filter(email=email).exists():
        return error_response(409, "EMAIL_DUPLICATED")

    if purpose == "PASSWORD_RESET":
        user = User.objects.filter(email=email).first()
        if user is None or not user.is_active:
            return error_response(404, "USER_NOT_FOUND")
        if user.login_type != User.LoginType.EMAIL:
            return error_response(403, "SOCIAL_ACCOUNT_NO_PASSWORD")

    now = timezone.now()

    current = _get_verification(email, purpose)
    if isinstance(current, dict):
        resend_available_at = datetime.fromisoformat(
            str(current["resend_available_at"]),
        )
        if now < resend_available_at:
            return error_response(429, "EMAIL_VERIFICATION_RATE_LIMITED")

    code = _generate_code()
    expires_at = now + timedelta(seconds=VERIFICATION_EXPIRES_SECONDS)
    resend_available_at = now + timedelta(seconds=VERIFICATION_RESEND_SECONDS)

    _save_verification(
        email,
        purpose,
        {
            "email": email,
            "purpose": purpose,
            "code_hash": _hash_code(code),
            "expires_at": expires_at.isoformat(),
            "resend_available_at": resend_available_at.isoformat(),
            "attempts": 0,
            "verified_until": None,
        },
        ttl=VERIFICATION_EXPIRES_SECONDS,
    )

    send_mail(
        subject="[Mongle] 이메일 인증 코드",
        message=f"인증 코드는 {code} 입니다. 3분 안에 입력해 주세요.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@mongle.local"),
        recipient_list=[email],
        fail_silently=False,
    )

    return JsonResponse(
        {
            "expires_in_seconds": VERIFICATION_EXPIRES_SECONDS,
            "resend_available_in_seconds": VERIFICATION_RESEND_SECONDS,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def confirm_email_verification(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        email = validate_email(body.get("email"))
        purpose = validate_purpose(body.get("purpose"))
        code = validate_verification_code(body.get("code"))
    except ValidationError as exc:
        return validation_error_response(exc)

    verification = _get_verification(email, purpose)
    if not isinstance(verification, dict):
        return error_response(400, "INVALID_VERIFICATION_CODE")

    if verification.get("email") != email or verification.get("purpose") != purpose:
        return error_response(400, "INVALID_VERIFICATION_CODE")

    attempts = int(verification.get("attempts", 0))
    if attempts >= VERIFICATION_MAX_ATTEMPTS:
        return error_response(429, "VERIFICATION_ATTEMPT_LIMITED")

    expires_at = datetime.fromisoformat(str(verification["expires_at"]))
    if timezone.now() > expires_at:
        return error_response(400, "VERIFICATION_CODE_EXPIRED")

    expected_hash = str(verification.get("code_hash", ""))
    if not constant_time_compare(expected_hash, _hash_code(code)):
        verification["attempts"] = attempts + 1
        remaining = max(
            1,
            int(
                (
                    datetime.fromisoformat(str(verification["expires_at"]))
                    - timezone.now()
                ).total_seconds()
            ),
        )
        _save_verification(email, purpose, verification, ttl=remaining)
        return error_response(400, "INVALID_VERIFICATION_CODE")

    _delete_verification(email, purpose)

    verification_token = secrets.token_urlsafe(32)
    _save_verified_token(verification_token, email, purpose)

    verified_until = timezone.now() + timedelta(seconds=VERIFICATION_VERIFIED_SECONDS)

    return JsonResponse(
        {
            "email": email,
            "purpose": purpose.lower(),
            "verified": True,
            "verified_until": _isoformat(verified_until),
            "verification_token": verification_token,
        },
    )


@csrf_exempt
@require_POST
def signup(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        payload = _validate_signup_payload(body)
    except ValidationError as exc:
        return validation_error_response(exc)

    raw_token = body.get("verification_token")
    verification_token = raw_token if isinstance(raw_token, str) and raw_token else ""
    token_data = _get_verified_token(verification_token) if verification_token else None
    if (
        not token_data
        or token_data.get("email") != payload["email"]
        or token_data.get("purpose") != "SIGNUP"
    ):
        return error_response(400, "EMAIL_NOT_VERIFIED")

    if User.objects.filter(email=payload["email"]).exists():
        return error_response(409, "EMAIL_DUPLICATED")

    with transaction.atomic():
        user = User.objects.create_user(
            email=payload["email"],
            password=payload["password"],
            user_name=payload["user_name"],
            job=payload["job"],
            birth=payload["birth"],
            is_aiconsent=payload["is_aiconsent"],
        )

    _delete_verified_token(verification_token)

    return JsonResponse(
        {
            "user_id": str(user.user_id),
            "email": user.email,
            "user_name": user.user_name,
            "token_balance": user.token_balance,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def password_reset(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        email = validate_email(body.get("email"))
        new_password = validate_password(body.get("new_password"))
    except ValidationError as exc:
        return validation_error_response(exc)

    social_user = (
        User.objects.filter(email=email)
        .exclude(login_type=User.LoginType.EMAIL)
        .first()
    )
    if social_user is not None:
        return error_response(403, "SOCIAL_ACCOUNT_NO_PASSWORD")

    raw_token = body.get("verification_token")
    verification_token = raw_token if isinstance(raw_token, str) and raw_token else ""
    token_data = _get_verified_token(verification_token) if verification_token else None
    if (
        not token_data
        or token_data.get("email") != email
        or token_data.get("purpose") != "PASSWORD_RESET"
    ):
        return error_response(400, "EMAIL_NOT_VERIFIED")

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return error_response(400, "EMAIL_NOT_VERIFIED")

    user.set_password(new_password)
    user.save(update_fields=["password"])
    # 비밀번호 재설정 시 전 기기의 자동로그인 토큰을 무효화한다(스펙).
    # 재설정은 비인증 흐름이라 새 비밀번호로 재로그인해야 한다.
    revoke_all_user_tokens(user)
    _delete_verified_token(verification_token)

    return JsonResponse({}, status=200)


def _validate_signup_payload(body: dict[str, Any]) -> dict[str, Any]:
    validators: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("email", lambda: validate_email(body.get("email"))),
        ("password", lambda: validate_password(body.get("password"))),
        ("user_name", lambda: validate_user_name(body.get("user_name"))),
        ("job", lambda: validate_optional_string(body.get("job"), "job", 20)),
        ("birth", lambda: validate_birth(body.get("birth"))),
        (
            "is_aiconsent",
            lambda: validate_required_boolean(
                body.get("is_aiconsent"),
                "is_aiconsent",
            ),
        ),
    )
    return collect_validated_fields(validators)
