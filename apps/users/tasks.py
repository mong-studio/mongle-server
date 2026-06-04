from __future__ import annotations

from django.utils import timezone

from celery import shared_task


@shared_task
def send_reflection_notification() -> None:
    """
    [스케줄] 매일 자정 실행
    활성화된 모든 유저에게 하루 회고 작성 알림을 발송한다.
    알림은 notifications 테이블에 저장되며, 앱에서 확인할 수 있다.
    """
    from apps.users.models import Notification, User

    today = timezone.localdate()
    users = User.objects.filter(is_active=True)

    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                type="reflection",
                title="하루 회고를 작성해주세요",
                content=f"{today} 하루는 어떠셨나요? 회고를 작성하고 토큰을 받아보세요.",  # noqa: E501
            )
            for user in users
        ]
    )
