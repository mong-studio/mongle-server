"""Todos 앱 테스트 - TODO 목록, 상세"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.models import Todo


# 비로그인 상태에서 TODO 목록 조회 시 401 반환 확인
@pytest.mark.django_db
def test_todo_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/todos/")
    assert response.status_code == 401


# TODO가 없을 때 빈 배열 반환 확인
@pytest.mark.django_db
def test_todo_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert response.json() == []


# 본인의 TODO만 목록에 포함되는지 확인
@pytest.mark.django_db
def test_todo_list_returns_own_todos(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["content"] == "테스트TODO"


# TODO 목록을 todo_date 쿼리로 필터링하는지 확인
@pytest.mark.django_db
def test_todo_list_filters_by_todo_date(
    auth_client: APIClient, todo: Todo, tag: Tag
) -> None:
    Todo.objects.create(
        user=todo.user,
        tag=tag,
        content="오늘TODO",
        todo_date="2026-06-03",
    )

    response = auth_client.get("/api/v1/todos/", {"todo_date": "2026-06-03"})

    assert response.status_code == 200
    body = response.json()
    assert [item["content"] for item in body] == ["오늘TODO"]


# TODO 목록 응답에 연결된 퀘스트 정보가 함께 포함되는지 확인
@pytest.mark.django_db
def test_todo_list_includes_assigned_quest(
    auth_client: APIClient, todo: Todo, quest: Quest
) -> None:
    response = auth_client.get("/api/v1/todos/")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["quest"]["quest_id"] == str(quest.quest_id)
    assert body[0]["quest"]["content"] == quest.content
    assert body[0]["quest"]["character_id"] == str(quest.character_id)
    assert body[0]["quest"]["character_name"] == quest.character.character_name


# 비로그인 상태에서 TODO 상세 조회 시 401 반환 확인
@pytest.mark.django_db
def test_todo_detail_unauthenticated(todo: Todo) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 401


# TODO 상세 조회 성공 시 content 필드가 올바른지 확인
@pytest.mark.django_db
def test_todo_detail_authenticated(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 200
    assert response.json()["content"] == "테스트TODO"


# 존재하지 않는 todo_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_todo_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404


# tag_id 없이 생성 시 태그 없이(null) 그대로 생성한다
@pytest.mark.django_db
def test_todo_create_without_tag_is_tagless(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/todos/",
        {"content": "태그없음", "todo_date": "2026-06-02"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["tag_id"] is None
    assert response.json()["tag_content"] is None


# tag_id를 명시하면 생성 성공
@pytest.mark.django_db
def test_todo_create_with_tag(auth_client: APIClient, tag: Tag) -> None:
    response = auth_client.post(
        "/api/v1/todos/",
        {"content": "할일", "todo_date": "2026-06-02", "tag_id": tag.tag_id},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["tag_content"] == tag.content


# TODO 완료 처리 시 연결된 퀘스트도 완료 상태로 변경되는지 확인
@pytest.mark.django_db
def test_todo_complete_marks_linked_quest_completed(
    auth_client: APIClient, todo: Todo, quest: Quest
) -> None:
    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/complete/")

    assert response.status_code == 200
    todo.refresh_from_db()
    quest.refresh_from_db()
    assert todo.status == Todo.Status.COMPLETED
    assert quest.status == Quest.Status.COMPLETED
