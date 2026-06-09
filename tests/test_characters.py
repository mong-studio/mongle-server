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


# S3 presigned PUT URL이 정상 발급되고 source_img_id와 upload URL이 응답에 포함되는지 확인
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


# 허용되지 않는 content_type(image/gif)으로 요청 시 400 반환 확인
@pytest.mark.django_db
def test_source_image_create_invalid_content_type(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/characters/source-images/",
        {"file_name": "photo.gif", "content_type": "image/gif", "content_length": 1024},
        format="json",
    )
    assert response.status_code == 400


# 파일 크기가 5MB 초과일 때 400 반환 확인
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


# 비로그인 상태에서 요청 시 401 반환 확인
@pytest.mark.django_db
def test_source_image_create_unauthenticated() -> None:
    client = APIClient()
    response = client.post("/api/v1/characters/source-images/", {}, format="json")
    assert response.status_code == 401


# ─── CHAR-002: Generation Job 생성 (Celery mocking) ─────────────────────────


# 정상 요청 시 job이 queued 상태로 생성되고 202 응답 확인
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


# 오늘 이미 3회 생성한 경우 429 응답 확인 (일일 생성 한도 초과)
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


# 이미 활성 캐릭터가 10개인 경우 422 응답 확인 (캐릭터 최대 보유 수 초과)
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


# succeeded 상태 job 조회 시 result에 gen_img_url이 포함되는지 확인
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


# 존재하지 않는 job_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_generation_job_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/generation-jobs/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404


# 비로그인 상태에서 job 조회 시 401 반환 확인
@pytest.mark.django_db
def test_generation_job_detail_unauthenticated(
    succeeded_job: CharacterGenerationJob,
) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/characters/generation-jobs/{succeeded_job.job_id}/")
    assert response.status_code == 401


# ─── CHAR-004: 캐릭터 등록 ──────────────────────────────────────────────────


# succeeded job으로 캐릭터 등록 성공 시 201 반환 및 job 상태가 consumed로 변경되는지 확인
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


# 이미 consumed된 job으로 재등록 시도 시 409 반환 확인
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


# queued(미완료) 상태의 job으로 등록 시도 시 400 반환 확인
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


# 비로그인 상태에서 목록 조회 시 401 반환 확인
@pytest.mark.django_db
def test_character_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/characters/")
    assert response.status_code == 401


# 캐릭터가 없는 경우 빈 목록과 has_next=false 반환 확인
@pytest.mark.django_db
def test_character_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["page"]["has_next"] is False


# 활성 캐릭터 2개가 목록에 모두 포함되는지 확인
@pytest.mark.django_db
def test_character_list_returns_active_characters(
    auth_client: APIClient, character: Character, second_character: Character
) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


# is_active=False인 캐릭터는 목록에서 제외되는지 확인
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


# 비로그인 상태에서 상세 조회 시 401 반환 확인
@pytest.mark.django_db
def test_character_detail_unauthenticated(character: Character) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 401


# 캐릭터 상세 조회 성공 시 character_id, character_name, active_quests 포함 확인
@pytest.mark.django_db
def test_character_detail_success(auth_client: APIClient, character: Character) -> None:
    response = auth_client.get(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["character_id"] == str(character.character_id)
    assert data["character_name"] == "테스트캐릭터"
    assert "active_quests" in data


# 존재하지 않는 character_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_character_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404


# ─── CHAR-007: 캐릭터 삭제 ──────────────────────────────────────────────────


# 캐릭터가 2개 이상일 때 삭제 성공 시 204 반환 및 is_active=False로 변경 확인
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


# 마지막 남은 캐릭터 삭제 시도 시 409와 LAST_CHARACTER 에러 반환 확인
@pytest.mark.django_db
def test_character_delete_last_character_rejected(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.delete(
        f"/api/v1/characters/{character.character_id}/delete/"
    )
    assert response.status_code == 409
    assert response.json()["error"] == "LAST_CHARACTER"


# 존재하지 않는 character_id 삭제 시도 시 404 반환 확인
@pytest.mark.django_db
def test_character_delete_not_found(auth_client: APIClient) -> None:
    response = auth_client.delete(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/delete/"
    )
    assert response.status_code == 404


# ─── QUES-001: 퀘스트 목록 ──────────────────────────────────────────────────


# IN_PROGRESS 퀘스트 1개가 목록에 포함되고 status 필드가 올바른지 확인
@pytest.mark.django_db
def test_quest_list_success(
    auth_client: APIClient, character: Character, quest: Quest
) -> None:
    response = auth_client.get(f"/api/v1/characters/{character.character_id}/quests/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "IN_PROGRESS"


# status=COMPLETED 필터 적용 시 IN_PROGRESS 퀘스트는 제외되는지 확인
@pytest.mark.django_db
def test_quest_list_filter_by_status(
    auth_client: APIClient, character: Character, quest: Quest
) -> None:
    response = auth_client.get(
        f"/api/v1/characters/{character.character_id}/quests/?status=COMPLETED"
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


# 존재하지 않는 character_id로 퀘스트 목록 조회 시 404 반환 확인
@pytest.mark.django_db
def test_quest_list_character_not_found(auth_client: APIClient) -> None:
    response = auth_client.get(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/quests/"
    )
    assert response.status_code == 404
