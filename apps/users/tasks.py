from __future__ import annotations

import datetime
import itertools

from django.utils import timezone

from celery import shared_task


@shared_task
def send_reflection_notification() -> None:
    """
    [스케줄] 매일 자정 실행
    활성화된 모든 유저에게 하루 회고 작성 알림을 발송한다.
    알림은 notifications 테이블에 저장되며, 앱에서 확인할 수 있다.
    - 중복 실행 방지: 오늘 이미 발송된 유저 제외
    - 메모리 효율: iterator + 1000개 단위 청크 처리
    """
    from apps.users.models import Notification, User

    today = timezone.localdate()
    today_start = timezone.make_aware(
        datetime.datetime.combine(today, datetime.time.min)
    )

    already_notified = Notification.objects.filter(
        type="reflection",
        created_at__gte=today_start,
    ).values_list("user_id", flat=True)

    user_pks = (
        User.objects.filter(is_active=True)
        .exclude(pk__in=already_notified)
        .values_list("pk", flat=True)
    )

    for pk_chunk in itertools.batched(user_pks.iterator(chunk_size=1000), 1000):
        Notification.objects.bulk_create(
            [
                Notification(
                    user_id=pk,
                    type="reflection",
                    title="하루 회고를 작성해주세요",
                    content=f"{today} 회고를 작성하고 토큰을 받아보세요.",
                )
                for pk in pk_chunk
            ]
        )


@shared_task
def cleanup_expired_refresh_tokens() -> None:
    """[스케줄] 매일 00:03 실행 — 만료된 refresh token 행 일괄 삭제."""
    from apps.users.models import RefreshToken

    RefreshToken.objects.filter(expires_at__lt=timezone.now()).delete()
