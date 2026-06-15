"""Characters API 테스트 - CHAR-001~007, QUES-001"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import override_settings
import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character, CharacterGenerationJob
from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.models import Todo
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
@override_settings(AWS_S3_PREFIX="mongle-village")
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
    # 런타임 객체는 공통 네임스페이스 아래로 모은다(IAM mongle-village/* 와 일치).
    assert data["object_key"].startswith("mongle-village/source-images/")


@override_settings(AWS_S3_PREFIX="mongle-village")
def test_with_prefix_prepends_namespace() -> None:
    from infrastructure.storage.s3 import with_prefix

    assert (
        with_prefix("source-images/u/x.png") == "mongle-village/source-images/u/x.png"
    )


@override_settings(AWS_S3_PREFIX="")
def test_with_prefix_noop_when_empty() -> None:
    from infrastructure.storage.s3 import with_prefix

    assert with_prefix("source-images/u/x.png") == "source-images/u/x.png"


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


# presigned URL이 글로벌(s3.amazonaws.com)이 아니라 리전 가상호스팅 엔드포인트로
# 서명되는지 확인 — 글로벌이면 S3가 리전 호스트로 301 리다이렉트해 브라우저 PUT이
# "cross-origin redirection"으로 차단된다.
@override_settings(
    AWS_S3_BUCKET="test-bucket",
    AWS_S3_REGION="ap-northeast-2",
    AWS_ACCESS_KEY_ID="AKIATEST",
    AWS_SECRET_ACCESS_KEY="secret",
)
def test_presigned_url_uses_regional_virtual_hosted_endpoint() -> None:
    from urllib.parse import parse_qs, urlparse

    from infrastructure.storage.s3 import generate_presigned_put_url

    result = generate_presigned_put_url(
        object_key="source-images/u/x.png",
        content_type="image/png",
        content_length=1024,
    )
    parsed = urlparse(result["url"])
    assert parsed.netloc == "test-bucket.s3.ap-northeast-2.amazonaws.com"

    # Content-Length 는 서명 헤더에 포함하지 않는다 — 브라우저가 임의로 설정하는
    # 금지 헤더라, 서명에 넣으면 403 SignatureDoesNotMatch 가 난다.
    signed = parse_qs(parsed.query)["X-Amz-SignedHeaders"][0]
    assert signed == "content-type;host"
    assert result["headers"] == {"Content-Type": "image/png"}


# AWS_S3_BUCKET 미설정 시 botocore 500 대신 503/명확한 에러 코드 반환 확인
@pytest.mark.django_db
@override_settings(AWS_S3_BUCKET="")
def test_source_image_create_storage_not_configured(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/characters/source-images/",
        {
            "file_name": "photo.jpg",
            "content_type": "image/jpeg",
            "content_length": 102400,
        },
        format="json",
    )
    assert response.status_code == 503
    assert response.json()["error"] == "STORAGE_NOT_CONFIGURED"


# ─── CHAR-002: Generation Job 생성 (Celery mocking) ─────────────────────────


# 정상 요청 시 job이 queued 상태로 생성되고 202 응답 확인
@pytest.mark.django_db
def test_generation_job_create_success(auth_client: APIClient) -> None:
    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {
                "name": "몽글",
                "persona": "착한 곰",
                "personality_keywords": ["활발한", "긍정적인"],
            },
            format="json",
        )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "QUEUED"
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
            {"name": "몽글", "persona": "착한 곰", "personality_keywords": ["활발한"]},
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
            {"name": "몽글", "persona": "착한 곰", "personality_keywords": ["활발한"]},
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
    assert data["status"] == "SUCCEEDED"
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
        "/api/v1/characters/",
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


# 등록 시 job의 custom_prompt가 Character.visual로 저장되는지 확인
@pytest.mark.django_db
def test_character_register_saves_custom_prompt_as_visual(
    auth_client: APIClient, user: User
) -> None:
    job = CharacterGenerationJob.objects.create(
        user=user,
        personality_keywords=["활발한"],
        status=CharacterGenerationJob.Status.SUCCEEDED,
        gen_img_url="https://example.com/gen.png",
        persona="밝은 캐릭터",
        custom_prompt="둥근 얼굴에 노란 털",
    )
    response = auth_client.post(
        "/api/v1/characters/",
        {"gen_job_id": str(job.job_id), "name": "몽글", "persona": "밝은"},
        format="json",
    )
    assert response.status_code == 201
    character = Character.objects.get(character_id=response.json()["character_id"])
    assert character.visual == "둥근 얼굴에 노란 털"


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
        "/api/v1/characters/",
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
        "/api/v1/characters/",
        {"gen_job_id": str(job.job_id), "name": "캐릭터", "persona": "페르소나"},
        format="json",
    )
    assert response.status_code == 400


# POST /characters로 등록 후 DELETE /characters/:id로 삭제하는 REST 흐름 확인
@pytest.mark.django_db
def test_register_via_post_collection_and_delete_via_delete(
    auth_client: APIClient,
    succeeded_job: CharacterGenerationJob,
    character: Character,
) -> None:
    # register: POST /characters (character fixture provides the "last character" guard bypass)
    resp = auth_client.post(
        "/api/v1/characters/",
        {"gen_job_id": str(succeeded_job.job_id), "name": "몽글", "persona": "착한 곰"},
        format="json",
    )
    assert resp.status_code == 201
    cid = resp.json()["character_id"]
    # delete: DELETE /characters/:id
    resp = auth_client.delete(f"/api/v1/characters/{cid}/")
    assert resp.status_code in (200, 204)


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
    assert response.json() == {
        "items": [],
        "page": {
            "limit": 20,
            "next_cursor": None,
            "has_next": False,
        },
    }


# 활성 캐릭터 2개가 목록에 모두 포함되는지 확인
@pytest.mark.django_db
def test_character_list_returns_active_characters(
    auth_client: APIClient, character: Character, second_character: Character
) -> None:
    response = auth_client.get("/api/v1/characters/")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


# IN_PROGRESS 퀘스트만 active_quest_count에 집계되는지 확인
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


# limit=1로 첫 페이지 조회 후 cursor로 다음 페이지 조회 정상 동작 확인
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


# 잘못된 cursor 값으로 요청 시 400 반환 확인
@pytest.mark.django_db
def test_character_list_rejects_invalid_cursor(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/characters/?cursor=not-a-valid-cursor")

    assert response.status_code == 400
    assert response.json() == {"error": "INVALID_CURSOR"}


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


# 캐릭터 상세 조회 성공 시 active_quests에 IN_PROGRESS 퀘스트만 포함되는지 확인
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
    assert payload["name"] == "테스트캐릭터"
    assert payload["active_quests"] == [
        {
            "quest_id": payload["active_quests"][0]["quest_id"],
            "todo_id": str(active_todo.todo_id),
            "title": "기획서 초안 쓰기",
        }
    ]


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
    response = auth_client.delete(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 204
    character.refresh_from_db()
    assert character.is_active is False


# 마지막 남은 캐릭터 삭제 시도 시 409와 LAST_CHARACTER 에러 반환 확인
@pytest.mark.django_db
def test_character_delete_last_character_rejected(
    auth_client: APIClient, character: Character
) -> None:
    response = auth_client.delete(f"/api/v1/characters/{character.character_id}/")
    assert response.status_code == 409
    assert response.json()["error"] == "LAST_CHARACTER"


# 존재하지 않는 character_id 삭제 시도 시 404 반환 확인
@pytest.mark.django_db
def test_character_delete_not_found(auth_client: APIClient) -> None:
    response = auth_client.delete(
        "/api/v1/characters/00000000-0000-0000-0000-000000000000/"
    )
    assert response.status_code == 404


# ─── CHAR-002 (추가): name·persona 수신 및 태스크 전달 ──────────────────────


@pytest.mark.django_db
def test_create_job_requires_name_persona_and_passes_to_task(
    auth_client: APIClient,
) -> None:
    with patch(
        "apps.characters.views.process_character_generation_job.delay"
    ) as mock_delay:
        resp = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"name": "몽글", "persona": "착한 곰", "personality_keywords": ["다정한"]},
            format="json",
        )
    assert resp.status_code == 202
    args = mock_delay.call_args.args
    assert args[1] == "몽글" and args[2] == "착한 곰"


# ─── TASK: Celery 태스크 AI 계약 정합 ───────────────────────────────────────


@pytest.mark.django_db
def test_process_job_calls_ai_v1_character_and_maps_image_url(
    user: User, settings
) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    fake = MagicMock()
    fake.json.return_value = {
        "status": "done",
        "result": {"image_url": "https://cdn/x.png"},
        "error": None,
    }
    fake.raise_for_status.return_value = None

    with patch("apps.characters.tasks.httpx.post", return_value=fake) as mock_post:
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    called_url = mock_post.call_args.args[0]
    called_kwargs = mock_post.call_args.kwargs
    assert called_url == "http://ai.test/v1/character"
    assert called_kwargs["headers"] == {"X-API-Key": "secret-key"}
    assert called_kwargs["json"]["name"] == "몽글"
    assert called_kwargs["json"]["persona"] == "착한 곰"
    assert called_kwargs["json"]["personality_keywords"] == ["다정한"]

    job.refresh_from_db()
    assert job.status == "SUCCEEDED"
    assert job.gen_img_url == "https://cdn/x.png"


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
