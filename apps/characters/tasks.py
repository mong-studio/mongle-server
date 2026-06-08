from __future__ import annotations

import datetime

from django.utils import timezone

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
