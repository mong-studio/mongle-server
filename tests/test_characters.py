"""Characters 앱 테스트 - 캐릭터 목록, 상세"""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character
from apps.quests.models import Quest
from apps.todos.models import Tag, Todo
from apps.users.models import User


@pytest.mark.django_db
def test_character_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/characters/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": {
            "limit": 20,
            "next_cursor": None,
            "has_next": False,
        },
    }


@pytest.mark.django_db
def test_character_list_returns_own_characters(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["items"]) == 1
    assert payload["items"][0]["character_name"] == "테스트캐릭터"
    assert payload["items"][0]["name"] == "테스트캐릭터"
    assert payload["items"][0]["active_quest_count"] == 0
    assert payload["page"]["has_next"] is False


@pytest.mark.django_db
def test_character_list_includes_active_quest_count(
    auth_client: APIClient,
    user: User,
    tag: Tag,
    character: Character,
) -> None:
    active_todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="진행 중 TODO",
        todo_date=date(2026, 6, 2),
        status=Todo.Status.IN_PROGRESS,
    )
    completed_todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="완료 TODO",
        todo_date=date(2026, 6, 2),
        status=Todo.Status.COMPLETED,
    )
    Quest.objects.create(
        character=character,
        todo=active_todo,
        content="진행 중 퀘스트",
    )
    Quest.objects.create(
        character=character,
        todo=completed_todo,
        content="완료 퀘스트",
    )

    response = auth_client.get("/api/v1/characters/")

    assert response.status_code == 200
    assert response.json()["items"][0]["active_quest_count"] == 1


@pytest.mark.django_db
def test_character_list_uses_cursor_pagination(
    auth_client: APIClient, user: User
) -> None:
    first_character = Character.objects.create(
        user=user,
        character_name="첫 번째",
        gen_img_url="https://example.com/1.png",
        persona="첫 번째 페르소나",
    )
    second_character = Character.objects.create(
        user=user,
        character_name="두 번째",
        gen_img_url="https://example.com/2.png",
        persona="두 번째 페르소나",
    )

    first_response = auth_client.get("/api/v1/characters/?limit=1")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert len(first_payload["items"]) == 1
    assert first_payload["items"][0]["character_id"] == str(
        second_character.character_id
    )
    assert first_payload["page"]["has_next"] is True
    assert first_payload["page"]["next_cursor"] is not None

    second_response = auth_client.get(
        f"/api/v1/characters/?limit=1&cursor={first_payload['page']['next_cursor']}"
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert len(second_payload["items"]) == 1
    assert second_payload["items"][0]["character_id"] == str(
        first_character.character_id
    )
    assert second_payload["page"]["has_next"] is False


@pytest.mark.django_db
def test_character_list_rejects_invalid_cursor(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/characters/?cursor=not-a-valid-cursor")

    assert response.status_code == 400
    assert response.json() == {"cursor": "유효하지 않은 cursor 입니다."}


@pytest.mark.django_db
def test_character_detail_unauthenticated(character: Character) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_detail_authenticated(
    auth_client: APIClient,
    user: User,
    tag: Tag,
    character: Character,
) -> None:
    active_todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="기획서 초안 쓰기",
        todo_date=date(2026, 6, 2),
        status=Todo.Status.IN_PROGRESS,
    )
    Quest.objects.create(character=character, todo=active_todo, content="초안 완성하기")
    response = auth_client.get(f"/api/v1/characters/{character.character_id}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["character_name"] == "테스트캐릭터"
    assert payload["name"] == "테스트캐릭터"
    assert payload["active_quests"] == [
        {
            "quest_id": payload["active_quests"][0]["quest_id"],
            "todo_id": str(active_todo.todo_id),
            "title": "기획서 초안 쓰기",
        }
    ]


@pytest.mark.django_db
def test_character_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404
