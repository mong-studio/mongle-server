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


def _compose_persona(result: dict) -> str:
    """AI 가 생성한 성격/말투/배경을 하나의 persona 텍스트로 합친다.

    빈 필드는 건너뛴다. 셋 다 비면 빈 문자열을 반환한다.
    """
    sections = (
        ("성격", result.get("personality", "")),
        ("말투", result.get("speech_style", "")),
        ("배경", result.get("background", "")),
    )
    return "\n".join(f"[{label}] {value}" for label, value in sections if value).strip()


def _save_generation_audit_log(
    *,
    user_id: str,
    job_id: str,
    name: str,
    persona: str,
    personality_keywords: list,
    result: dict,
    elapsed_seconds: float,
) -> None:
    """compose 로 버려지는 생성 원본(유저 입력 + LLM raw 출력)을 S3 에 보존한다.

    best-effort: S3 미설정/네트워크 오류로 실패해도 생성 잡은 막지 않는다.
    키: log/character-gen/dt={YYYY-MM-DD}/{user_id}/{job_id}.json (with_prefix 하위).
    데이터 종류(log)를 최상위 세그먼트로 두어 이미지와 분리 → Lifecycle/IAM 별도 적용,
    dt= 날짜 파티션으로 Lifecycle 만료·Athena 파티션 스캔을 쉽게 한다.
    """
    try:
        from infrastructure.storage.s3 import put_json, with_prefix

        now = timezone.now()
        put_json(
            with_prefix(f"log/character-gen/dt={now:%Y-%m-%d}/{user_id}/{job_id}.json"),
            {
                "logged_at": now.isoformat(),
                "user_id": user_id,
                "job_id": job_id,
                "input": {
                    "name": name,
                    "persona": persona,
                    "personality_keywords": personality_keywords,
                },
                "ai_result": result,
                "composed_persona": _compose_persona(result),
                # 서버 end-to-end(초). 단계별 분리는 ai_result["timings"] 참고.
                "server_elapsed_seconds": elapsed_seconds,
            },
        )
    except Exception:
        logger.warning(
            "character generation audit log 저장 실패: job_id=%s", job_id, exc_info=True
        )


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
    self, job_id: str, name: str, persona: str, img_gen_log_id: int | None = None
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

        # 서버 관점 end-to-end 소요시간(submit→done). AI 가 돌려주는 단계별
        # ai_result["timings"](llm_persona/image_generator)와 함께 로그에 남긴다.
        started = time.monotonic()

        # 1) 등록(submit) → 즉시 ai_job_id 수신(202)
        ai_job_id = _submit_character_job(
            base_url=base_url, payload=payload, headers=headers
        )

        # 2) 폴링(poll) → 완료 시 result(엔티티)
        result = _poll_character_result(
            base_url=base_url, ai_job_id=ai_job_id, headers=headers
        )

        # compose 단계에서 버려지는 구조화 데이터(유저 원본 입력 + LLM raw 출력)를
        # 감사 로그로 S3 에 보존한다. best-effort — 실패해도 생성 잡은 계속 진행한다.
        _save_generation_audit_log(
            user_id=str(job.user_id),
            job_id=str(job.job_id),
            name=name,
            persona=persona,
            personality_keywords=job.personality_keywords,
            result=result,
            elapsed_seconds=round(time.monotonic() - started, 2),
        )

        job.gen_img_url = result.get("image_url", "")
        job.gen_img_object_key = result.get("gen_img_object_key", "")
        job.appearance = result.get("appearance", "")
        job.persona = _compose_persona(result)
        job.status = CharacterGenerationJob.Status.SUCCEEDED
        job.save(
            update_fields=[
                "gen_img_url",
                "gen_img_object_key",
                "appearance",
                "persona",
                "status",
                "updated_at",
            ]
        )

    except Exception:
        logger.exception("character generation job failed: job_id=%s", job_id)
        job.status = CharacterGenerationJob.Status.FAILED
        job.save(update_fields=["status", "updated_at"])
        # 생성 실패 시 제출 시점에 차감했던 일일 생성 횟수를 환불한다(해당 로그만 삭제).
        if img_gen_log_id is not None:
            from apps.characters.models import ImgGenLog

            ImgGenLog.objects.filter(pk=img_gen_log_id).delete()
