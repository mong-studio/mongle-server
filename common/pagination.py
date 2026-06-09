"""Shared pagination helpers."""

from __future__ import annotations

import base64
import json
from typing import Any

from django.db.models import QuerySet


def encode_cursor(created_at: str, pk: str) -> str:
    payload = json.dumps({"created_at": created_at, "pk": pk})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> dict[str, str]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        data: dict[str, str] = json.loads(payload)
    except Exception as e:
        raise ValueError("INVALID_CURSOR") from e
    if "created_at" not in data or "pk" not in data:
        raise ValueError("INVALID_CURSOR")
    return data


def paginate_queryset(
    qs: QuerySet[Any],
    pk_field: str,
    limit: int,
    cursor: str | None,
) -> tuple[list[Any], str | None, bool]:
    """
    cursor 기반 페이지네이션.

    Returns (items, next_cursor, has_next).
    """
    if cursor:
        data = decode_cursor(cursor)
        qs = qs.filter(created_at__lt=data["created_at"]) | qs.filter(
            created_at=data["created_at"],
            **{f"{pk_field}__lt": data["pk"]},
        )

    qs = qs.order_by("-created_at", f"-{pk_field}")
    items = list(qs[: limit + 1])
    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(
            last.created_at.isoformat(),
            str(getattr(last, pk_field)),
        )

    return items, next_cursor, has_next
