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
    from apps.quests.models import Quest
    from apps.todos.models import Todo

    today = timezone.localdate()
    failed_todo_ids = list(
        Todo.objects.filter(
            todo_date=today,
            status=Todo.Status.IN_PROGRESS,
        ).values_list("todo_id", flat=True)
    )

    if not failed_todo_ids:
        return

    Todo.objects.filter(todo_id__in=failed_todo_ids).update(status=Todo.Status.FAILED)
    Quest.objects.filter(
        todo_id__in=failed_todo_ids,
        status=Todo.Status.IN_PROGRESS,
    ).update(status=Todo.Status.FAILED)
