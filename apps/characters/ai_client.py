"""mongle-ai character API bridge."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib import error, request
from urllib.parse import urlparse
from uuid import uuid4


class CharacterAIClientError(RuntimeError):
    """Raised when mongle-ai returns an error or invalid payload."""


@dataclass
class CharacterAIClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 15.0

    def create(
        self,
        *,
        user_id: str,
        name: str,
        persona: str,
        personality_keywords: list[str],
        source_image_url: str | None,
    ) -> dict[str, Any]:
        return self._post(
            "/v1/character",
            {
                "user_id": user_id,
                "name": name,
                "persona": persona,
                "personality_keywords": personality_keywords,
                "source_image_url": source_image_url,
            },
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        parsed_base_url = urlparse(self.base_url)
        if parsed_base_url.scheme not in {"http", "https"}:
            raise CharacterAIClientError("mongle-ai base URL must use http or https")

        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid4()),
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["X-Internal-Service-Token"] = self.api_key

        req = request.Request(  # noqa: S310 - scheme is validated just above
            self.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
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
            raise CharacterAIClientError(
                f"mongle-ai HTTP {err.code}: {detail[:200]}"
            ) from err
        except error.URLError as err:
            raise CharacterAIClientError(f"mongle-ai connection failed: {err}") from err
        except json.JSONDecodeError as err:
            raise CharacterAIClientError(
                "mongle-ai returned non-JSON response"
            ) from err

        if body.get("status") != "done":
            raise CharacterAIClientError(
                f"mongle-ai returned non-done envelope: {body}"
            )

        result = body.get("result")
        if not isinstance(result, dict):
            raise CharacterAIClientError("mongle-ai result payload is missing")
        return result
