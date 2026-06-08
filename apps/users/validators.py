"""User signup input validation helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
import json
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.http import HttpRequest

EMAIL_VALIDATOR = EmailValidator()
PASSWORD_PATTERN_GROUPS = (
    re.compile(r"[A-Za-z]"),
    re.compile(r"\d"),
    re.compile(r"[^A-Za-z0-9\s]"),
)
USER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9가-힣]{2,8}$")


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError({"body": ["JSON 형식이 올바르지 않습니다."]}) from exc

    if not isinstance(body, dict):
        raise ValidationError({"body": ["JSON object를 입력해 주세요."]})

    return body


def validate_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError({"email": ["이메일을 입력해 주세요."]})

    email = value.strip().lower()
    try:
        EMAIL_VALIDATOR(email)
    except ValidationError as exc:
        raise ValidationError({"email": ["올바른 이메일 형식이 아닙니다."]}) from exc

    return email


def validate_purpose(value: object) -> str:
    if value not in {"SIGNUP", "PASSWORD_RESET"}:
        raise ValidationError({"purpose": ["지원하지 않는 인증 목적입니다."]})
    return str(value)


def validate_verification_code(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{6}", value):
        raise ValidationError({"code": ["인증 코드는 영문 대문자 6자리입니다."]})
    return value


def validate_password(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError({"password": ["비밀번호를 입력해 주세요."]})
    if (
        len(value) < 8
        or len(value) > 16
        or any(character.isspace() for character in value)
    ):
        raise ValidationError({"password": ["비밀번호는 공백 없이 8~16자여야 합니다."]})

    matched_groups = sum(
        1 for pattern in PASSWORD_PATTERN_GROUPS if pattern.search(value)
    )
    if matched_groups < 2:
        raise ValidationError(
            {"password": ["영문, 숫자, 특수문자 중 최소 2종류를 조합해 주세요."]},
        )

    return value


def validate_user_name(value: object) -> str:
    if not isinstance(value, str) or not USER_NAME_PATTERN.fullmatch(value):
        raise ValidationError(
            {"user_name": ["닉네임은 한글, 영문, 숫자 2~8자로 입력해 주세요."]},
        )
    return value


def validate_optional_string(value: object, field: str, max_length: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError({field: ["문자열로 입력해 주세요."]})
    stripped = value.strip()
    if len(stripped) > max_length:
        raise ValidationError({field: [f"{max_length}자 이하로 입력해 주세요."]})
    return stripped


def validate_optional_birth(value: object) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError({"birth": ["YYYY-MM-DD 형식으로 입력해 주세요."]})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(
            {"birth": ["YYYY-MM-DD 형식으로 입력해 주세요."]},
        ) from exc


def validate_required_boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError({field: ["boolean 값을 입력해 주세요."]})
    return value


def collect_validated_fields(
    validators: tuple[tuple[str, Callable[[], object]], ...],
) -> dict[str, object]:
    """필드별 validator를 실행해 에러를 모아 한 번에 ValidationError로 raise."""
    payload: dict[str, object] = {}
    errors: dict[str, list[str]] = {}
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
