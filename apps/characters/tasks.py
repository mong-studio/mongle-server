from __future__ import annotations

import datetime

from django.utils import timezone
import httpx

from celery import shared_task


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
        source_img_url = ""
        if job.source_image and job.source_image.object_key:
            source_img_url = (
                f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_S3_REGION}"
                f".amazonaws.com/{job.source_image.object_key}"
            )

        payload = {
            "user_id": str(job.user_id),
            "name": name,
            "persona": persona,
            "personality_keywords": job.personality_keywords,
            "source_image_url": source_img_url,
        }

        response = httpx.post(
            f"{settings.AI_SERVICE_URL}/v1/character",
            json=payload,
            headers={"X-API-Key": settings.AI_SERVICE_TOKEN},
            timeout=120.0,
        )
        response.raise_for_status()
        result = response.json().get("result") or {}

        job.gen_img_url = result.get("image_url", "")
        job.gen_img_object_key = result.get("gen_img_object_key", "")
        job.status = CharacterGenerationJob.Status.SUCCEEDED
        job.save(
            update_fields=["gen_img_url", "gen_img_object_key", "status", "updated_at"]
        )

    except Exception as exc:
        job.status = CharacterGenerationJob.Status.FAILED
        job.error_code = type(exc).__name__
        job.error_message = str(exc)[:255]
        job.save(update_fields=["status", "error_code", "error_message", "updated_at"])
