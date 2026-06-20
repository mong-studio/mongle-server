"""캘린더 일정 등록/조회/수정/삭제 엔드포인트 테스트 (REQ-PLAN-005~009)."""

from __future__ import annotations

import pytest

from apps.tags.models import Tag
from apps.todos.models import Schedule, Todo


@pytest.mark.django_db
def test_create_schedule_persists_and_returns_tag_info(auth_client, tag: Tag) -> None:
    response = auth_client.post(
        "/api/v1/schedules/",
        data={
            "title": "기말고사",
            "description": "수학 2단원",
            "start_date": "2026-06-20",
            "end_date": "2026-06-21",
            "tag_id": tag.tag_id,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Schedule.objects.count() == 1
    body = response.json()
    assert body["title"] == "기말고사"
    assert body["start_date"] == "2026-06-20"
    assert body["tag_content"] == tag.content
    assert body["tag_color"] == tag.color


@pytest.mark.django_db
def test_create_schedule_without_tag_falls_back_to_default(auth_client) -> None:
    response = auth_client.post(
        "/api/v1/schedules/",
        data={
            "title": "병원 예약",
            "start_date": "2026-06-25",
            "end_date": "2026-06-25",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Schedule.objects.get().tag.content == "기타"


@pytest.mark.django_db
def test_create_todo_without_tag_is_tagless(auth_client) -> None:
    response = auth_client.post(
        "/api/v1/todos/",
        data={"content": "운동", "todo_date": "2026-06-20"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Todo.objects.get().tag is None


@pytest.mark.django_db
def test_calendar_returns_todos_and_schedules_for_month(
    auth_client, user, tag: Tag
) -> None:
    Todo.objects.create(user=user, tag=tag, content="운동", todo_date="2026-06-18")
    Schedule.objects.create(
        user=user,
        tag=tag,
        title="시험",
        start_date="2026-06-20",
        end_date="2026-06-21",
    )
    # 다른 달 일정은 제외돼야 한다.
    Schedule.objects.create(
        user=user, tag=tag, title="여행", start_date="2026-07-01", end_date="2026-07-03"
    )

    response = auth_client.get("/api/v1/calendar/?year=2026&month=6")

    assert response.status_code == 200
    body = response.json()
    assert len(body["todos"]) == 1
    assert len(body["schedules"]) == 1
    assert body["schedules"][0]["title"] == "시험"


@pytest.mark.django_db
def test_fail_todo_marks_failed(auth_client, user, tag: Tag) -> None:
    todo = Todo.objects.create(
        user=user, tag=tag, content="운동", todo_date="2026-06-18"
    )

    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/fail/")

    assert response.status_code == 200
    todo.refresh_from_db()
    assert todo.status == Todo.Status.FAILED


@pytest.mark.django_db
def test_fail_non_in_progress_todo_conflicts(auth_client, user, tag: Tag) -> None:
    todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="운동",
        todo_date="2026-06-18",
        status=Todo.Status.COMPLETED,
    )

    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/fail/")

    assert response.status_code == 409


@pytest.mark.django_db
def test_calendar_rejects_bad_params(auth_client) -> None:
    assert auth_client.get("/api/v1/calendar/?year=2026").status_code == 400
    assert auth_client.get("/api/v1/calendar/?year=x&month=6").status_code == 400


@pytest.mark.django_db
def test_update_schedule_changes_fields(auth_client, user, tag: Tag) -> None:
    schedule = Schedule.objects.create(
        user=user, tag=tag, title="회의", start_date="2026-06-18", end_date="2026-06-18"
    )

    response = auth_client.patch(
        f"/api/v1/schedules/{schedule.schedule_id}/",
        data={"title": "주간 회의", "description": "스프린트 리뷰"},
        content_type="application/json",
    )

    assert response.status_code == 200
    schedule.refresh_from_db()
    assert schedule.title == "주간 회의"
    assert schedule.description == "스프린트 리뷰"


@pytest.mark.django_db
def test_delete_schedule_removes_it(auth_client, user, tag: Tag) -> None:
    schedule = Schedule.objects.create(
        user=user, tag=tag, title="회의", start_date="2026-06-18", end_date="2026-06-18"
    )

    response = auth_client.delete(f"/api/v1/schedules/{schedule.schedule_id}/")

    assert response.status_code == 204
    assert Schedule.objects.count() == 0


@pytest.mark.django_db
def test_schedule_is_scoped_to_owner(auth_client, django_user_model, tag: Tag) -> None:
    other = django_user_model.objects.create_user(
        email="other@test.com", password="pw123456", user_name="남", birth="2000-01-01"
    )
    other_tag = Tag.objects.create(tag_id=99, user=other, content="기타", color="#000")
    schedule = Schedule.objects.create(
        user=other, tag=other_tag, title="비밀", start_date="2026-06-18"
    )

    response = auth_client.delete(f"/api/v1/schedules/{schedule.schedule_id}/")

    assert response.status_code == 404
    assert Schedule.objects.count() == 1
