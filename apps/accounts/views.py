"""Account API views."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import secrets
import string
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.validators import (
    parse_json_body,
    validate_email,
    validate_optional_birth,
    validate_optional_string,
    validate_password,
    validate_purpose,
    validate_required_boolean,
    validate_user_name,
    validate_verification_code,
)

EMAIL_VERIFICATION_SESSION_KEY = "email_verification"
VERIFICATION_EXPIRES_SECONDS = 180
VERIFICATION_RESEND_SECONDS = 30
VERIFICATION_VERIFIED_SECONDS = 600
VERIFICATION_MAX_ATTEMPTS = 5


def _error_response(
    status: int,
    message: str,
    details: dict[str, list[str]] | None = None,
) -> JsonResponse:
    return JsonResponse(
        {
            "error": {
                "code": status,
                "message": message,
                "details": details or {},
            },
        },
        status=status,
    )


def _validation_error_response(exc: ValidationError) -> JsonResponse:
    details: dict[str, list[str]]
    if hasattr(exc, "message_dict"):
        details = {
            field: [str(message) for message in messages]
            for field, messages in exc.message_dict.items()
        }
    else:
        details = {"non_field_errors": [str(message) for message in exc.messages]}
    return _error_response(400, "VALIDATION_ERROR", details)


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
        return _validation_error_response(exc)

    if purpose == "SIGNUP" and User.objects.filter(email=email).exists():
        return _error_response(409, "EMAIL_DUPLICATED")

    now = timezone.now()
    current = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    if (
        isinstance(current, dict)
        and current.get("email") == email
        and current.get("purpose") == purpose
    ):
        resend_available_at = datetime.fromisoformat(
            str(current["resend_available_at"]),
        )
        if now < resend_available_at:
            return _error_response(429, "EMAIL_VERIFICATION_RATE_LIMITED")

    code = _generate_code()
    expires_at = now + timedelta(seconds=VERIFICATION_EXPIRES_SECONDS)
    resend_available_at = now + timedelta(seconds=VERIFICATION_RESEND_SECONDS)
    request.session[EMAIL_VERIFICATION_SESSION_KEY] = {
        "email": email,
        "purpose": purpose,
        "code_hash": _hash_code(code),
        "expires_at": expires_at.isoformat(),
        "resend_available_at": resend_available_at.isoformat(),
        "attempts": 0,
        "verified_until": None,
    }
    request.session.modified = True

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
        return _validation_error_response(exc)

    verification = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    if not isinstance(verification, dict):
        return _error_response(400, "INVALID_VERIFICATION_CODE")

    if verification.get("email") != email or verification.get("purpose") != purpose:
        return _error_response(400, "INVALID_VERIFICATION_CODE")

    attempts = int(verification.get("attempts", 0))
    if attempts >= VERIFICATION_MAX_ATTEMPTS:
        return _error_response(429, "VERIFICATION_ATTEMPT_LIMITED")

    expires_at = datetime.fromisoformat(str(verification["expires_at"]))
    if timezone.now() > expires_at:
        return _error_response(400, "VERIFICATION_CODE_EXPIRED")

    expected_hash = str(verification.get("code_hash", ""))
    if not constant_time_compare(expected_hash, _hash_code(code)):
        verification["attempts"] = attempts + 1
        request.session[EMAIL_VERIFICATION_SESSION_KEY] = verification
        request.session.modified = True
        return _error_response(400, "INVALID_VERIFICATION_CODE")

    verified_until = timezone.now() + timedelta(seconds=VERIFICATION_VERIFIED_SECONDS)
    verification["verified_until"] = verified_until.isoformat()
    verification.pop("code_hash", None)
    request.session[EMAIL_VERIFICATION_SESSION_KEY] = verification
    request.session.modified = True

    return JsonResponse(
        {
            "email": email,
            "purpose": purpose.lower(),
            "verified": True,
            "verified_until": _isoformat(verified_until),
        },
    )


@csrf_exempt
@require_POST
def signup(request: HttpRequest) -> JsonResponse:
    try:
        payload = _validate_signup_payload(parse_json_body(request))
    except ValidationError as exc:
        return _validation_error_response(exc)

    verification = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    if not _is_signup_email_verified(verification, payload["email"]):
        return _error_response(400, "EMAIL_NOT_VERIFIED")

    if User.objects.filter(email=payload["email"]).exists():
        return _error_response(409, "EMAIL_DUPLICATED")

    with transaction.atomic():
        user = User.objects.create_user(
            email=payload["email"],
            password=payload["password"],
            user_name=payload["user_name"],
            job=payload["job"],
            birth=payload["birth"],
            is_aiconsent=payload["is_aiconsent"],
        )

    request.session.pop(EMAIL_VERIFICATION_SESSION_KEY, None)
    request.session.modified = True

    return JsonResponse(
        {
            "user_id": str(user.id),
            "email": user.email,
            "user_name": user.user_name,
            "token_balance": user.token_balance,
        },
        status=201,
    )


def _validate_signup_payload(body: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}

    validators: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("email", lambda: validate_email(body.get("email"))),
        ("password", lambda: validate_password(body.get("password"))),
        ("user_name", lambda: validate_user_name(body.get("user_name"))),
        ("job", lambda: validate_optional_string(body.get("job"), "job", 50)),
        ("birth", lambda: validate_optional_birth(body.get("birth"))),
        (
            "is_aiconsent",
            lambda: validate_required_boolean(
                body.get("is_aiconsent"),
                "is_aiconsent",
            ),
        ),
    )
    for field, validator in validators:
        try:
            payload[field] = validator()
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                errors.update(
                    {
                        key: [str(message) for message in messages]
                        for key, messages in exc.message_dict.items()
                    },
                )
            else:
                errors[field] = [str(message) for message in exc.messages]

    if errors:
        raise ValidationError(errors)

    return payload


def _is_signup_email_verified(verification: object, email: str) -> bool:
    if not isinstance(verification, dict):
        return False
    if verification.get("email") != email or verification.get("purpose") != "SIGNUP":
        return False
    verified_until = verification.get("verified_until")
    if not verified_until:
        return False
    return timezone.now() <= datetime.fromisoformat(str(verified_until))


def no_content(_: HttpRequest) -> HttpResponse:
    return HttpResponse(status=204)
