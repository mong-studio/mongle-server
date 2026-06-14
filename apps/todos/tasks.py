from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from celery import shared_task


@shared_task
def fail_incomplete_todos() -> None:
    """[스케줄] 매일 자정 실행: 전날 IN_PROGRESS TODO를 FAILED로 변경한다."""
    from apps.todos.models import Todo

    target_date = timezone.localdate() - timedelta(days=1)
    Todo.objects.filter(
        todo_date=target_date,
        status=Todo.Status.IN_PROGRESS,
    ).update(status=Todo.Status.FAILED)
