"""Todos 앱 테스트 - TODO 목록, 상세"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.todos.models import Todo


@pytest.mark.django_db
def test_todo_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/todos/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_todo_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_todo_list_returns_own_todos(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["content"] == "테스트TODO"


@pytest.mark.django_db
def test_todo_detail_unauthenticated(todo: Todo) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_todo_detail_authenticated(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 200
    assert response.json()["content"] == "테스트TODO"


@pytest.mark.django_db
def test_todo_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404
