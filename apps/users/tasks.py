from __future__ import annotations

import datetime
from datetime import timedelta
import itertools

from django.utils import timezone

from celery import shared_task


@shared_task
def send_reflection_notification() -> None:
    """
    [스케줄] 매일 자정 실행
    전날 실패한 TODO가 있고 아직 회고하지 않은 유저에게 회고 작성 알림을 발송한다.
    알림은 notifications 테이블에 저장되며, 앱에서 확인할 수 있다.
    - 중복 실행 방지: 오늘 같은 회고 날짜로 이미 발송된 유저 제외
    - 메모리 효율: iterator + 1000개 단위 청크 처리
    """
    from apps.todos.models import Reflection, Todo
    from apps.users.models import Notification, User
    from apps.users.notification_service import create_reflection_notification

    target_date = timezone.localdate() - timedelta(days=1)
    today_start = timezone.make_aware(
        datetime.datetime.combine(timezone.localdate(), datetime.time.min)
    )

    already_notified = Notification.objects.filter(
        type="reflection",
        created_at__gte=today_start,
        data__reflection_date=target_date.isoformat(),
    ).values_list("user_id", flat=True)
    already_reflected = Reflection.objects.filter(
        reflection_date=target_date
    ).values_list("user_id", flat=True)
    users_with_failed_todos = Todo.objects.filter(
        todo_date=target_date,
        status=Todo.Status.FAILED,
    ).values_list("user_id", flat=True)

    user_pks = (
        User.objects.filter(is_active=True)
        .filter(pk__in=users_with_failed_todos)
        .exclude(pk__in=already_notified)
        .exclude(pk__in=already_reflected)
        .values_list("pk", flat=True)
    )

    for pk_chunk in itertools.batched(user_pks.iterator(chunk_size=1000), 1000):
        for user in User.objects.filter(pk__in=pk_chunk):
            create_reflection_notification(user=user, reflection_date=target_date)


@shared_task
def cleanup_expired_refresh_tokens() -> None:
    """[스케줄] 매일 00:03 실행 — 만료된 refresh token 행 일괄 삭제."""
    from apps.users.models import RefreshToken

    RefreshToken.objects.filter(expires_at__lt=timezone.now()).delete()
