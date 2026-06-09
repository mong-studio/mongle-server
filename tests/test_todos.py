"""Todos 앱 테스트 - TODO 목록, 상세"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

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
