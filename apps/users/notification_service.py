from __future__ import annotations

from datetime import date

from apps.todos.models import Reflection
from apps.users.models import Notification, User

REFLECTION_NOTIFICATION_TYPE = "reflection"


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
        title="하루 회고를 작성해주세요",
        content=f"{reflection_date_text} 회고를 작성하고 토큰을 받아보세요.",
        data={"target": "reflection", "reflection_date": reflection_date_text},
    )
