"""Auth API 공통 에러 응답 형식: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import JsonResponse


def error_response(
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


def validation_error_response(exc: ValidationError) -> JsonResponse:
    details: dict[str, list[str]]
    if hasattr(exc, "message_dict"):
        details = {
            field: [str(message) for message in messages]
            for field, messages in exc.message_dict.items()
        }
    else:
        details = {"non_field_errors": [str(message) for message in exc.messages]}
    return error_response(400, "VALIDATION_ERROR", details)
