from __future__ import annotations

from datetime import date
import uuid

from apps.todos.models import Reflection
from apps.users.models import Notification, User

REFLECTION_NOTIFICATION_TYPE = "reflection"
FEED_NOTIFICATION_TYPE = "feed"


def create_feed_post_notification(
    *, user: User, character_name: str, caption: str, post_id: uuid.UUID | str
) -> Notification:
    """피드(마을 게시판 글)가 생성되면 작성 캐릭터의 주인에게 알림을 남긴다.

    reflection 알림과 동일하게 Notification 한 건을 만들고, 프론트는 폴링으로 받아
    토스트 + 알림창에 함께 띄운다. type/data 필드만 쓰므로 스키마 변경이 없다.
    """
    return Notification.objects.create(
        user=user,
        type=FEED_NOTIFICATION_TYPE,
        title=f"{character_name}의 새 소식이 도착했어요!",
        content=caption,
        data={"target": "feed", "post_id": str(post_id)},
    )


def create_reflection_notification(
    *, user: User, reflection_date: date
) -> Notification | None:
    reflection_date_text = reflection_date.isoformat()
    if Reflection.objects.filter(
        user=user,
        reflection_date=reflection_date,
    ).exists():
        return None

    existing = Notification.objects.filter(
        user=user,
        type=REFLECTION_NOTIFICATION_TYPE,
        data__reflection_date=reflection_date_text,
    ).first()
    if existing is not None:
        return None

    return Notification.objects.create(
        user=user,
        type=REFLECTION_NOTIFICATION_TYPE,
        title="오늘도 고생 많았어요",
        content="오늘 하루를 같이 정리 해볼까요?",
        data={"target": "reflection", "reflection_date": reflection_date_text},
    )
