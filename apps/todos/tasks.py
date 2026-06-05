from __future__ import annotations

from django.utils import timezone

from celery import shared_task


@shared_task
def fail_incomplete_todos() -> None:
    """
    [스케줄] 매일 자정 실행
    오늘 날짜의 TODO 중 IN_PROGRESS 상태인 항목을 FAILED로 변경한다.
    연동된 퀘스트도 함께 실패 처리된다.
    """
    from apps.todos.models import Todo

    today = timezone.localdate()
    Todo.objects.filter(
        todo_date=today,
        status=Todo.Status.IN_PROGRESS,
    ).update(status=Todo.Status.FAILED)
