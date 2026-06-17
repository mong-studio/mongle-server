"""mongle-ai TODO / quest API bridge."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib import error, request
from urllib.parse import urlparse
from uuid import uuid4


class TodoAIClientError(RuntimeError):
    """Raised when mongle-ai returns an error or invalid payload."""


@dataclass
class TodoAIClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 15.0

    def generate(self, *, user_id: str, prompt: str, today: str) -> dict[str, Any]:
        payload = {"user_id": user_id, "prompt": prompt, "today": today}
        return self._post("/v1/todo/generate", payload)

    def chat(
        self, *, user_id: str, message: str, today: str, thread_id: str | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": "multi",
            "user_id": user_id,
            "message": message,
            "today": today,
        }
        if thread_id:
            payload["thread_id"] = thread_id
        return self._post("/v1/todo/chat", payload)

    def generate_quests(
        self,
        *,
        todos: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        remaining_daily_quota: int,
    ) -> dict[str, Any]:
        return self._post(
            "/v1/quest/generate",
            {
                "todos": todos,
                "characters": characters,
                "remaining_daily_quota": remaining_daily_quota,
                "shuffle_seed": None,
            },
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        parsed_base_url = urlparse(self.base_url)
        if parsed_base_url.scheme not in {"http", "https"}:
            raise TodoAIClientError("mongle-ai base URL must use http or https")

        raw = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid4()),
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["X-Internal-Service-Token"] = self.api_key
        req = request.Request(  # noqa: S310 - scheme is validated just above
            self.base_url.rstrip("/") + path,
            data=raw,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(  # noqa: S310 - scheme is validated just above
                req,
                timeout=self.timeout_seconds,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="ignore")
            raise TodoAIClientError(
                f"mongle-ai HTTP {err.code}: {detail[:200]}"
            ) from err
        except error.URLError as err:
            raise TodoAIClientError(f"mongle-ai connection failed: {err}") from err
        except json.JSONDecodeError as err:
            raise TodoAIClientError("mongle-ai returned non-JSON response") from err

        if body.get("status") != "done":
            raise TodoAIClientError(f"mongle-ai returned non-done envelope: {body}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise TodoAIClientError("mongle-ai result payload is missing")
        return result
