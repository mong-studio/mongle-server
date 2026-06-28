from __future__ import annotations

from django.utils import timezone

from celery import shared_task


@shared_task
def fail_incomplete_todos() -> None:
    """[스케줄] 매일 자정 실행: 지난 날짜의 IN_PROGRESS TODO를 모두 FAILED로 변경한다.

    배치가 하루라도 거르거나 과거 날짜로 만든 TODO 때문에 '미완료'로 남는 일이
    없도록, 어제뿐 아니라 오늘 이전(todo_date < today) 전체를 대상으로 한다.
    """
    from apps.todos.models import Todo

    Todo.objects.filter(
        todo_date__lt=timezone.localdate(),
        status=Todo.Status.IN_PROGRESS,
    ).update(status=Todo.Status.FAILED)
