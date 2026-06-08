from __future__ import annotations

from django.utils import timezone

from celery import shared_task


@shared_task
def fail_incomplete_todos() -> None:
    """[스케줄] 매일 자정 실행: 오늘 날짜의 IN_PROGRESS TODO를 FAILED로 변경한다."""
    from apps.todos.models import Todo

    today = timezone.localdate()
    Todo.objects.filter(
        todo_date=today,
        status=Todo.Status.IN_PROGRESS,
    ).update(status=Todo.Status.FAILED)
