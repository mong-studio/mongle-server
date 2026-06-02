"""Characters 앱 테스트 - 캐릭터 목록, 상세"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character


@pytest.mark.django_db
def test_character_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/characters/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/characters/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_character_list_returns_own_characters(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.get("/api/characters/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["character_name"] == "테스트캐릭터"


@pytest.mark.django_db
def test_character_detail_unauthenticated(character: Character) -> None:
    client = APIClient()
    response = client.get(f"/api/characters/{character.character_id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_detail_authenticated(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.get(f"/api/characters/{character.character_id}/")
    assert response.status_code == 200
    assert response.json()["character_name"] == "테스트캐릭터"


@pytest.mark.django_db
def test_character_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/characters/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404
