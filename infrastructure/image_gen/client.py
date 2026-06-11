"""RunPod Serverless 이미지 생성 클라이언트.

IMAGE_PROVIDER=local  → 빈 문자열 반환 (개발용)
IMAGE_PROVIDER=runpod → RunPod /runsync 호출 후 base64 data URL 반환
"""

from __future__ import annotations

import json
from urllib import error, request
from uuid import uuid4


class ImageGenError(RuntimeError):
    """이미지 생성 실패 시 발생."""


def generate_character_image(
    *,
    api_key: str,
    endpoint_id: str,
    timeout_seconds: float,
    source_image_b64: str | None = None,
) -> str:
    """RunPod Serverless 워커를 동기 호출해 base64 data URL을 반환한다.

    endpoint_id 또는 api_key가 비어있으면 빈 문자열을 반환한다 (로컬 모드).
    """
    if not endpoint_id or not api_key:
        return ""

    url = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
    payload = json.dumps({"input": {"source_image_b64": source_image_b64}}).encode()
    req = request.Request(  # noqa: S310
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Request-Id": str(uuid4()),
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
            body = json.loads(resp.read().decode())
    except error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        raise ImageGenError(f"RunPod HTTP {err.code}: {detail[:200]}") from err
    except error.URLError as err:
        raise ImageGenError(f"RunPod 연결 실패: {err}") from err

    if body.get("status") != "COMPLETED":
        raise ImageGenError(f"RunPod 작업 실패: {body.get('status')}")

    image_b64 = (body.get("output") or {}).get("image_b64", "")
    if not image_b64:
        raise ImageGenError("RunPod 응답에 image_b64 없음")

    return f"data:image/png;base64,{image_b64}"
