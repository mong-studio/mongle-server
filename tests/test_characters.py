"""Characters API 테스트 - CHAR-001~007, QUES-001"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character, CharacterGenerationJob
from apps.quests.models import Quest
from apps.users.models import User


@pytest.fixture
def succeeded_job(db, user: User) -> CharacterGenerationJob:
    return CharacterGenerationJob.objects.create(
        user=user,
        personality_keywords=["활발한", "긍정적인"],
        status=CharacterGenerationJob.Status.SUCCEEDED,
        gen_img_url="https://example.com/gen.png",
        persona="밝고 활발한 캐릭터",
    )


@pytest.fixture
def second_character(db, user: User) -> Character:
    return Character.objects.create(
        user=user,
        character_name="두번째캐릭터",
        gen_img_url="https://example.com/img2.png",
        persona="두번째 페르소나",
    )


# ─── CHAR-001: Source Image (S3 mocking) ────────────────────────────────────


@pytest.mark.django_db
def test_source_image_create_success(auth_client: APIClient) -> None:
    with patch("infrastructure.storage.s3.get_s3_client") as mock_s3:
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "https://s3.example.com/presigned"
        )
        mock_s3.return_value = mock_client

        response = auth_client.post(
            "/api/v1/characters/source-images/",
            {
                "file_name": "photo.jpg",
                "content_type": "image/jpeg",
                "content_length": 102400,
            },
            format="json",
        )

    assert response.status_code == 201
    data = response.json()
    assert "source_img_id" in data
    assert "upload" in data
    assert data["upload"]["url"] == "https://s3.example.com/presigned"


@pytest.mark.django_db
def test_source_image_create_invalid_content_type(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/characters/source-images/",
        {"file_name": "photo.gif", "content_type": "image/gif", "content_length": 1024},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_source_image_create_too_large(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/characters/source-images/",
        {
            "file_name": "big.jpg",
            "content_type": "image/jpeg",
            "content_length": 6 * 1024 * 1024,
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_source_image_create_unauthenticated() -> None:
    client = APIClient()
    response = client.post("/api/v1/characters/source-images/", {}, format="json")
    assert response.status_code == 401


# ─── CHAR-002: Generation Job 생성 (Celery mocking) ─────────────────────────


@pytest.mark.django_db
def test_generation_job_create_success(auth_client: APIClient) -> None:
    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"personality_keywords": ["활발한", "긍정적인"]},
            format="json",
        )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert "job_id" in data


@pytest.mark.django_db
def test_generation_job_create_daily_limit_exceeded(
    auth_client: APIClient, user: User
) -> None:
    from apps.characters.models import ImgGenLog

    for i in range(3):
        ImgGenLog.objects.create(user=user, gen_cnt=i + 1)

    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"personality_keywords": ["활발한"]},
            format="json",
        )
    assert response.status_code == 429


@pytest.mark.django_db
def test_generation_job_create_character_limit_exceeded(
    auth_client: APIClient, user: User
) -> None:
    for i in range(10):
        Character.objects.create(
            user=user,
            character_name=f"캐릭터{i}",
            gen_img_url="https://example.com/img.png",
            persona="페르소나",
        )

    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"personality_keywords": ["활발한"]},
            format="json",
        )
    assert response.status_code == 422


# ─── CHAR-003: Generation Job 조회 ──────────────────────────────────────────


@pytest.mark.django_db
def test_generation_job_detail_returns_succeeded_job(
    auth_client: APIClient, succeeded_job: CharacterGenerationJob
) -> None:
    response = auth_client.get(
        f"/api/v1/characters/generation-jobs/{succeeded_job.job_id}/"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == str(succeeded_job.job_id)
    assert data["status"] == "succeeded"
    assert data["result"]["gen_img_url"] == "https://example.com/gen.png"


@pytest.mark.django_db
def test_generation_job_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/generation-jobs/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_generation_job_detail_unauthenticated(
    succeeded_job: CharacterGenerationJob,
) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/characters/generation-jobs/{succeeded_job.job_id}/")
    assert response.status_code == 401


# ─── CHAR-004: 캐릭터 등록 ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_character_register_success(
    auth_client: APIClient, succeeded_job: CharacterGenerationJob
) -> None:
    response = auth_client.post(
        "/api/v1/characters/register/",
        {
            "gen_job_id": str(succeeded_job.job_id),
            "name": "내 캐릭터",
            "persona": "밝고 활발한",
        },
        format="json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "내 캐릭터"
    assert "character_id" in data

    succeeded_job.refresh_from_db()
    assert succeeded_job.status == CharacterGenerationJob.Status.CONSUMED


@pytest.mark.django_db
def test_character_register_job_already_consumed(
    auth_client: APIClient, user: User
) -> None:
    job = CharacterGenerationJob.objects.create(
        user=user,
        personality_keywords=["활발한"],
        status=CharacterGenerationJob.Status.CONSUMED,
        gen_img_url="https://example.com/gen.png",
        persona="페르소나",
    )
    response = auth_client.post(
        "/api/v1/characters/register/",
        {"gen_job_id": str(job.job_id), "name": "캐릭터", "persona": "페르소나"},
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_character_register_job_not_succeeded(
    auth_client: APIClient, user: User
) -> None:
    job = CharacterGenerationJob.objects.create(
        user=user,
        personality_keywords=["활발한"],
        status=CharacterGenerationJob.Status.QUEUED,
    )
    response = auth_client.post(
        "/api/v1/characters/register/",
        {"gen_job_id": str(job.job_id), "name": "캐릭터", "persona": "페르소나"},
        format="json",
    )
    assert response.status_code == 400


# ─── CHAR-005: 캐릭터 목록 ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_character_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/characters/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["page"]["has_next"] is False


@pytest.mark.django_db
def test_character_list_returns_active_characters(
    auth_client: APIClient, character: Character, second_character: Character
) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


@pytest.mark.django_db
def test_character_list_excludes_inactive(
    auth_client: APIClient, character: Character
) -> None:
    character.is_active = False
    character.save()
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


# ─── CHAR-006: 캐릭터 상세 ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_character_detail_unauthenticated(character: Character) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_character_detail_success(auth_client: APIClient, character: Character) -> None:
    response = auth_client.get(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["character_id"] == str(character.character_id)
    assert data["character_name"] == "테스트캐릭터"
    assert "active_quests" in data


@pytest.mark.django_db
def test_character_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404


# ─── CHAR-007: 캐릭터 삭제 ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_character_delete_success(
    auth_client: APIClient, character: Character, second_character: Character
) -> None:
    response = auth_client.delete(
        f"/api/v1/characters/{character.character_id}/delete/"
    )
    assert response.status_code == 204
    character.refresh_from_db()
    assert character.is_active is False


@pytest.mark.django_db
def test_character_delete_last_character_rejected(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.delete(
        f"/api/v1/characters/{character.character_id}/delete/"
    )
    assert response.status_code == 409
    assert response.json()["error"] == "LAST_CHARACTER"


@pytest.mark.django_db
def test_character_delete_not_found(auth_client: APIClient) -> None:
    response = auth_client.delete(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/delete/"
    )
    assert response.status_code == 404


# ─── QUES-001: 퀘스트 목록 ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_quest_list_success(
    auth_client: APIClient, character: Character, quest: Quest
) -> None:
    response = auth_client.get(f"/api/v1/characters/{character.character_id}/quests/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "IN_PROGRESS"


@pytest.mark.django_db
def test_quest_list_filter_by_status(
    auth_client: APIClient, character: Character, quest: Quest
) -> None:
    response = auth_client.get(
        f"/api/v1/characters/{character.character_id}/quests/?status=COMPLETED"
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


@pytest.mark.django_db
def test_quest_list_character_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/quests/"
    )
    assert response.status_code == 404
