"""mongle-ai TODO / quest API bridge."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

# generate/chat 의 planner LLM 은 RunPod Pod 프록시(100s)를 넘기므로
# mongle-ai 가 submit(202)+poll(GET) 비동기 잡으로 응답한다.
# 개별 요청은 짧게, 전체는 폴링으로 기다려 100s 벽을 우회한다.
_SUBMIT_POLL_REQUEST_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 2.0


class TodoAIClientError(RuntimeError):
    """Raised when mongle-ai returns an error or invalid payload."""


@dataclass
class TodoAIClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 15.0

    def generate(self, *, user_id: str, prompt: str, today: str) -> dict[str, Any]:
        payload = {"user_id": user_id, "prompt": prompt, "today": today}
        return self._submit_and_poll(
            submit_path="/v1/todo/generate",
            poll_prefix="/v1/todo/generate",
            payload=payload,
        )

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
        return self._submit_and_poll(
            submit_path="/v1/todo/chat",
            poll_prefix="/v1/todo/chat",
            payload=payload,
        )

    def generate_quests(
        self,
        *,
        todos: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        remaining_daily_quota: int,
    ) -> dict[str, Any]:
        # 퀘스트 분배 LLM 은 캐릭터 수만큼 순차 호출되어 Pod 100s 프록시를 넘기므로
        # generate/chat 과 동일하게 submit(202)+poll(GET) 로 100s 벽을 우회한다.
        return self._submit_and_poll(
            submit_path="/v1/quest/generate",
            poll_prefix="/v1/quest/generate",
            payload={
                "todos": todos,
                "characters": characters,
                "remaining_daily_quota": remaining_daily_quota,
                "shuffle_seed": None,
            },
        )

    def _submit_and_poll(
        self, *, submit_path: str, poll_prefix: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """submit(202)→job_id→poll(GET) 루프로 done 결과(dict)를 반환한다.

        개별 요청은 짧은 타임아웃, 전체 대기는 self.timeout_seconds 까지 폴링한다.
        Pod 프록시 100s 하드 타임아웃을 개별 요청이 넘지 않게 분리한다.
        """
        submit = self._request("POST", submit_path, payload=payload)
        job_id = (submit.get("result") or {}).get("job_id")
        if not job_id:
            raise TodoAIClientError(
                f"mongle-ai submit 응답에 job_id 가 없습니다: {submit}"
            )

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            body = self._request("GET", f"{poll_prefix}/{job_id}")
            job_status = body.get("status")
            if job_status == "done":
                return self._unwrap_result(body)
            if job_status == "error":
                error_body = body.get("error") or {}
                raise TodoAIClientError(
                    f"mongle-ai 생성 실패: "
                    f"{error_body.get('code')} {error_body.get('message')}"
                )
            if time.monotonic() >= deadline:
                raise TodoAIClientError("mongle-ai 폴링 타임아웃")
            time.sleep(_POLL_INTERVAL_SECONDS)

    @staticmethod
    def _unwrap_result(body: dict[str, Any]) -> dict[str, Any]:
        result = body.get("result")
        if not isinstance(result, dict):
            raise TodoAIClientError("mongle-ai result payload is missing")
        return result

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """mongle-ai 에 단일 HTTP 요청을 보내고 파싱한 봉투(dict)를 반환한다."""
        parsed_base_url = urlparse(self.base_url)
        if parsed_base_url.scheme not in {"http", "https"}:
            raise TodoAIClientError("mongle-ai base URL must use http or https")

        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid4()),
            # RunPod Pod 프록시(*.proxy.runpod.net)는 Cloudflare 뒤라 기본
            # urllib UA(Python-urllib/*)를 1010으로 막는다. 서비스 UA로 통과.
            "User-Agent": "mongle-server/1.0",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["X-Internal-Service-Token"] = self.api_key

        try:
            response = httpx.request(
                method,
                self.base_url.rstrip("/") + path,
                json=payload,
                headers=headers,
                timeout=timeout or _SUBMIT_POLL_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as err:
            detail = err.response.text
            raise TodoAIClientError(
                f"mongle-ai HTTP {err.response.status_code}: {detail[:200]}"
            ) from err
        except httpx.RequestError as err:
            raise TodoAIClientError(f"mongle-ai connection failed: {err}") from err
        except ValueError as err:
            raise TodoAIClientError("mongle-ai returned non-JSON response") from err

        if not isinstance(body, dict):
            raise TodoAIClientError("mongle-ai returned a non-object envelope")
        return body
