from __future__ import annotations

import datetime
import logging
import time

from django.utils import timezone
import httpx

from celery import shared_task

logger = logging.getLogger(__name__)

# mongle-ai 는 RunPod Pod 프록시(100s 타임아웃) 뒤에 있어 /v1/character 를
# 등록(202)+폴링(GET) 비동기로 호출한다. 개별 요청은 짧게, 폴링은 길게 둔다.
_REQUEST_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 300.0


def _submit_character_job(
    *, base_url: str, payload: dict, headers: dict[str, str]
) -> str:
    """mongle-ai 에 생성을 등록하고 ai_job_id 를 반환한다."""
    response = httpx.post(
        f"{base_url}/v1/character",
        json=payload,
        headers=headers,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    ai_job_id = ((response.json() or {}).get("result") or {}).get("job_id")
    if not ai_job_id:
        raise RuntimeError("mongle-ai submit 응답에 job_id 가 없습니다")
    return str(ai_job_id)


def _poll_character_result(
    *, base_url: str, ai_job_id: str, headers: dict[str, str]
) -> dict:
    """mongle-ai 잡을 완료까지 폴링하고 result(dict)를 반환한다.

    done → result 반환, error → 예외, 타임아웃 → 예외.
    """
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while True:
        response = httpx.get(
            f"{base_url}/v1/character/{ai_job_id}",
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json() or {}
        job_status = body.get("status")

        if job_status == "done":
            return body.get("result") or {}
        if job_status == "error":
            error = body.get("error") or {}
            raise RuntimeError(
                f"mongle-ai 생성 실패: {error.get('code')} {error.get('message')}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError("mongle-ai 캐릭터 생성 폴링 타임아웃")
        time.sleep(_POLL_INTERVAL_SECONDS)


@shared_task
def reset_image_gen_count() -> None:
    """
    [스케줄] 매일 자정 실행
    오늘 이전 날짜의 이미지 재생성 이력(ImgGenLog)을 삭제하여
    카운트를 초기화한다. 계정당 하루 3회 제한이며 다음날 다시 가능해진다.
    """
    from apps.characters.models import ImgGenLog

    today_start = timezone.make_aware(
        datetime.datetime.combine(timezone.localdate(), datetime.time.min)
    )
    ImgGenLog.objects.filter(created_at__lt=today_start).delete()


@shared_task(bind=True, max_retries=3)
def process_character_generation_job(
    self, job_id: str, name: str, persona: str
) -> None:
    """AI 서비스(/v1/character)에 캐릭터 생성 요청을 보내고 결과를 저장한다."""
    from django.conf import settings

    from apps.characters.models import CharacterGenerationJob

    try:
        job = CharacterGenerationJob.objects.get(pk=job_id)
    except CharacterGenerationJob.DoesNotExist:
        return

    job.status = CharacterGenerationJob.Status.IN_PROGRESS
    job.save(update_fields=["status", "updated_at"])

    try:
        # mongle-ai 는 source_image_key(S3 object key)로 원본 이미지를 boto3 fetch 한다.
        # source_image_url 은 메타데이터용이라 key 없이 url 만 보내면 이미지가 무시된다.
        source_image_key = ""
        source_image_content_type = ""
        source_img_url = ""
        if job.source_image and job.source_image.object_key:
            source_image_key = job.source_image.object_key
            source_image_content_type = job.source_image.content_type
            source_img_url = (
                f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_S3_REGION}"
                f".amazonaws.com/{source_image_key}"
            )

        payload = {
            "user_id": str(job.user_id),
            "name": name,
            "persona": persona,
            "personality_keywords": job.personality_keywords,
            "source_image_key": source_image_key,
            "source_image_content_type": source_image_content_type,
            "source_image_url": source_img_url,
        }

        base_url = settings.AI_SERVICE_URL
        headers = {"X-API-Key": settings.AI_SERVICE_TOKEN}

        # 1) 등록(submit) → 즉시 ai_job_id 수신(202)
        ai_job_id = _submit_character_job(
            base_url=base_url, payload=payload, headers=headers
        )

        # 2) 폴링(poll) → 완료 시 result(엔티티)
        result = _poll_character_result(
            base_url=base_url, ai_job_id=ai_job_id, headers=headers
        )

        job.gen_img_url = result.get("image_url", "")
        job.gen_img_object_key = result.get("gen_img_object_key", "")
        job.appearance = result.get("appearance", "")
        job.status = CharacterGenerationJob.Status.SUCCEEDED
        job.save(
            update_fields=[
                "gen_img_url",
                "gen_img_object_key",
                "appearance",
                "status",
                "updated_at",
            ]
        )

    except Exception:
        logger.exception("character generation job failed: job_id=%s", job_id)
        job.status = CharacterGenerationJob.Status.FAILED
        job.save(update_fields=["status", "updated_at"])
