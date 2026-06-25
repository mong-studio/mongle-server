"""Characters API 테스트 - CHAR-001~007, QUES-001"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character, CharacterGenerationJob, SourceImage
from apps.posts.models import Post
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
@override_settings(AWS_S3_PREFIX="mongle-village", AWS_S3_BUCKET="test-bucket")
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


@pytest.mark.django_db
def test_generation_job_normalizes_personality_keyword_alias(
    auth_client: APIClient,
) -> None:
    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {
                "name": "몽글",
                "persona": "궁금한 게 많은 곰",
                "personality_keywords": ["호기심 많은"],
            },
            format="json",
        )

    assert response.status_code == 202
    job = CharacterGenerationJob.objects.get(job_id=response.json()["job_id"])
    assert job.personality_keywords == ["호기심많은"]


# 최근 24시간 안에 이미 3회 생성한 경우 429 응답 확인
@pytest.mark.django_db
def test_generation_job_create_daily_limit_exceeded(
    auth_client: APIClient, user: User
) -> None:
    from apps.characters.models import ImgGenLog

    now = timezone.now()
    created_at_values = [
        now - timedelta(hours=3),
        now - timedelta(hours=2),
        now - timedelta(hours=1),
    ]
    for i, created_at in enumerate(created_at_values):
        log = ImgGenLog.objects.create(user=user, gen_cnt=i + 1)
        ImgGenLog.objects.filter(pk=log.pk).update(created_at=created_at)

    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"name": "몽글", "persona": "착한 곰", "personality_keywords": ["활발한"]},
            format="json",
        )
    assert response.status_code == 429
    data = response.json()
    assert data["error"] == "DAILY_GENERATION_LIMIT_EXCEEDED"
    assert "reset_at" in data
    assert isinstance(data["retry_after_seconds"], int)
    assert 20 * 60 * 60 < data["retry_after_seconds"] <= 21 * 60 * 60


# 생성 횟수 조회 시 최근 24시간의 used 와 limit 을 반환하는지 확인
@pytest.mark.django_db
def test_generation_quota_returns_used_and_limit(
    auth_client: APIClient, user: User
) -> None:
    from apps.characters.models import ImgGenLog

    old_log = ImgGenLog.objects.create(user=user, gen_cnt=1)
    ImgGenLog.objects.filter(pk=old_log.pk).update(
        created_at=timezone.now() - timedelta(hours=25)
    )
    ImgGenLog.objects.create(user=user, gen_cnt=2)
    ImgGenLog.objects.create(user=user, gen_cnt=3)

    response = auth_client.get("/api/v1/characters/generation-jobs/quota/")

    assert response.status_code == 200
    data = response.json()
    assert data["used"] == 2
    assert data["limit"] == 3
    assert "reset_at" in data
    assert isinstance(data["retry_after_seconds"], int)


# 비로그인 상태에서 생성 횟수 조회 시 401 반환 확인
@pytest.mark.django_db
def test_generation_quota_unauthenticated() -> None:
    response = APIClient().get("/api/v1/characters/generation-jobs/quota/")
    assert response.status_code == 401


def _create_generation_job(auth_client: APIClient) -> str:
    """생성 잡을 만들고(태스크 실행은 막음) job_id 를 반환한다."""
    with patch("apps.characters.tasks.process_character_generation_job.delay"):
        response = auth_client.post(
            "/api/v1/characters/generation-jobs/",
            {"name": "몽글", "persona": "착한 곰", "personality_keywords": ["활발한"]},
            format="json",
        )
    assert response.status_code == 202
    return str(response.json()["job_id"])


def _used(auth_client: APIClient) -> int:
    return int(
        auth_client.get("/api/v1/characters/generation-jobs/quota/").json()["used"]
    )


# 생성 중 취소하면 차감했던 일일 생성 횟수가 환불(ImgGenLog 삭제)되는지 확인
@pytest.mark.django_db
def test_cancel_refunds_daily_generation_count(
    auth_client: APIClient, user: User
) -> None:
    from apps.characters.models import ImgGenLog

    job_id = _create_generation_job(auth_client)
    assert _used(auth_client) == 1  # 제출 시 1회 차감

    cancel = auth_client.post(f"/api/v1/characters/generation-jobs/{job_id}/cancel/")

    assert cancel.status_code == 200
    assert cancel.json()["status"] == "FAILED"
    assert _used(auth_client) == 0  # 환불되어 0
    assert ImgGenLog.objects.filter(user=user).count() == 0


# 이미 완료(SUCCEEDED)된 잡은 취소 불가(409)이고 횟수도 유지되는지 확인
@pytest.mark.django_db
def test_cancel_rejected_and_count_kept_when_succeeded(
    auth_client: APIClient, user: User
) -> None:
    from apps.characters.models import ImgGenLog

    job_id = _create_generation_job(auth_client)
    job = CharacterGenerationJob.objects.get(job_id=job_id)
    job.status = CharacterGenerationJob.Status.SUCCEEDED
    job.save(update_fields=["status"])

    cancel = auth_client.post(f"/api/v1/characters/generation-jobs/{job_id}/cancel/")

    assert cancel.status_code == 409
    # 캐릭터가 만들어진 잡이므로 횟수는 유지되어야 한다.
    assert _used(auth_client) == 1
    assert ImgGenLog.objects.filter(user=user).count() == 1


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


# 등록 시 job의 appearance(AI 생성 외형)가 Character.visual로 저장되는지 확인
@pytest.mark.django_db
def test_character_register_saves_appearance_as_visual(
    auth_client: APIClient, user: User
) -> None:
    job = CharacterGenerationJob.objects.create(
        user=user,
        personality_keywords=["활발한"],
        status=CharacterGenerationJob.Status.SUCCEEDED,
        gen_img_url="https://example.com/gen.png",
        persona="밝은 캐릭터",
        appearance="둥근 얼굴에 노란 털",
    )
    # 요청에 persona 를 보내도 무시되고, job 의 AI 정제본이 저장돼야 한다.
    response = auth_client.post(
        "/api/v1/characters/",
        {
            "gen_job_id": str(job.job_id),
            "name": "몽글",
            "persona": "사용자가 보낸 원본",
        },
        format="json",
    )
    assert response.status_code == 201
    character = Character.objects.get(character_id=response.json()["character_id"])
    assert character.visual == "둥근 얼굴에 노란 털"
    assert character.persona == "밝은 캐릭터"

    # 개인화 프로필(JSON)에 캐릭터 정보가 기록돼야 한다.
    user.refresh_from_db()
    assert user.personalization["character"]["persona"] == "밝은 캐릭터"
    assert user.personalization["character"]["name"] == "몽글"


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
    # 원본 사진 없이 만든 캐릭터는 origin_img_url 이 빈 문자열.
    assert payload["origin_img_url"] == ""
    # title 은 TODO 내용("기획서 초안 쓰기")이 아니라 퀘스트 제목이어야 한다.
    assert payload["active_quests"] == [
        {
            "quest_id": payload["active_quests"][0]["quest_id"],
            "todo_id": str(active_todo.todo_id),
            "title": "초안 완성하기",
        }
    ]
    # 피드(Post)가 없으면 feed_count 는 0.
    assert payload["feed_count"] == 0


@pytest.mark.django_db
def test_character_detail_returns_feed_count(
    auth_client: APIClient,
    user: User,
    tag: Tag,
    character: Character,
) -> None:
    todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="기획서 초안 쓰기",
        todo_date=date(2026, 6, 2),
        status=Todo.Status.IN_PROGRESS,
    )
    quest = Quest.objects.create(
        character=character, todo=todo, content="초안 완성하기"
    )
    Post.objects.create(
        character=character, quest=quest, content="피드1", img_url="https://x/1.png"
    )
    Post.objects.create(
        character=character, quest=quest, content="피드2", img_url="https://x/2.png"
    )

    response = auth_client.get(f"/api/v1/characters/{character.character_id}/")

    assert response.status_code == 200
    assert response.json()["feed_count"] == 2


# 상세 조회 시 persona 의 [성격] 구획만 추출한 personality 필드를 함께 내려주는지 확인
@pytest.mark.django_db
def test_character_detail_returns_extracted_personality(
    auth_client: APIClient, user: User
) -> None:
    char = Character.objects.create(
        user=user,
        character_name="구획캐릭터",
        gen_img_url="https://example.com/x.png",
        persona="[성격]\n다정하고 차분해요\n[말투]\n반말을 써요\n[배경]\n숲속 마을",
    )

    response = auth_client.get(f"/api/v1/characters/{char.character_id}/")

    assert response.status_code == 200
    data = response.json()
    # [성격] 구획 본문만 추출된다.
    assert data["personality"] == "다정하고 차분해요"
    # 원문 persona 도 그대로 함께 내려준다.
    assert data["persona"].startswith("[성격]")


def test_extract_personality_falls_back_to_full_text() -> None:
    from apps.characters.serializers import _extract_personality

    assert _extract_personality("[성격] 활발함 [말투] 존댓말") == "활발함"
    assert _extract_personality("그냥 한 줄 페르소나") == "그냥 한 줄 페르소나"
    assert _extract_personality("") == ""


# 이사 간(is_active=False) 캐릭터도 본인 소유면 상세 조회가 200으로 가능한지 확인
@pytest.mark.django_db
def test_character_detail_allows_inactive_owned_character(
    auth_client: APIClient, user: User
) -> None:
    char = Character.objects.create(
        user=user,
        character_name="이사간캐릭터",
        gen_img_url="https://example.com/x.png",
        persona="페르소나",
        is_active=False,
    )

    response = auth_client.get(f"/api/v1/characters/{char.character_id}/")

    assert response.status_code == 200
    assert response.json()["is_active"] is False


# 등록 시 origin_img_url 컬럼에 원본 사진의 S3 object_key가 저장되는지 확인
@pytest.mark.django_db
def test_character_register_stores_origin_object_key(
    auth_client: APIClient, user: User
) -> None:
    source_image = SourceImage.objects.create(
        user=user,
        object_key="mongle-village/source-images/u/abc.png",
        content_type="image/png",
        expires_at=timezone.now(),
    )
    job = CharacterGenerationJob.objects.create(
        user=user,
        source_image=source_image,
        personality_keywords=["활발한"],
        status=CharacterGenerationJob.Status.SUCCEEDED,
        gen_img_url="https://example.com/gen.png",
        persona="밝은 캐릭터",
    )
    response = auth_client.post(
        "/api/v1/characters/",
        {"gen_job_id": str(job.job_id), "name": "몽글", "persona": "x"},
        format="json",
    )

    assert response.status_code == 201
    character = Character.objects.get(character_id=response.json()["character_id"])
    # URL 이 아니라 object_key(불변)를 저장한다.
    assert character.origin_img_url == source_image.object_key


# 상세 조회 시 저장된 object_key를 presigned GET URL로 서명해 반환하는지 확인
@pytest.mark.django_db
def test_character_detail_presigns_origin_on_read(
    auth_client: APIClient, user: User
) -> None:
    object_key = "mongle-village/source-images/u/abc.png"
    character = Character.objects.create(
        user=user,
        character_name="몽글",
        origin_img_url=object_key,
        gen_img_url="https://example.com/gen.png",
        persona="밝은 캐릭터",
    )

    with patch(
        "infrastructure.storage.s3.generate_presigned_get_url",
        return_value="https://s3.example.com/origin-presigned",
    ) as mock_presign:
        response = auth_client.get(f"/api/v1/characters/{character.character_id}/")

    assert response.status_code == 200
    assert (
        response.json()["origin_img_url"] == "https://s3.example.com/origin-presigned"
    )
    assert mock_presign.call_args.args[0] == object_key


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


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


# 텍스트만: submit(202)→poll(done) 후 gen_img_url과 appearance가 저장되는지 확인
@pytest.mark.django_db
def test_process_job_submits_polls_and_saves_appearance(user: User, settings) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-1"}, "error": None}
    )
    poll = _mock_response(
        {
            "status": "done",
            "result": {"image_url": "https://cdn/x.png", "appearance": "둥근 갈색 몸"},
            "error": None,
        }
    )

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit) as mock_post,
        patch("apps.characters.tasks.httpx.get", return_value=poll) as mock_get,
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    # 등록 호출 검증
    assert mock_post.call_args.args[0] == "http://ai.test/v1/character"
    post_kwargs = mock_post.call_args.kwargs
    assert post_kwargs["headers"] == {"X-API-Key": "secret-key"}
    assert post_kwargs["json"]["name"] == "몽글"
    assert post_kwargs["json"]["persona"] == "착한 곰"
    assert post_kwargs["json"]["personality_keywords"] == ["다정한"]
    assert post_kwargs["json"]["source_image_url"] == ""
    # 폴링 호출 검증(submit 이 돌려준 job_id 로)
    assert mock_get.call_args.args[0] == "http://ai.test/v1/character/ai-1"

    job.refresh_from_db()
    assert job.status == "SUCCEEDED"
    assert job.gen_img_url == "https://cdn/x.png"
    assert job.appearance == "둥근 갈색 몸"


# 생성 실패 시 제출 시점에 차감한 일일 생성 횟수(ImgGenLog)가 환불(삭제)되는지 확인
@pytest.mark.django_db
def test_process_job_failure_refunds_gen_count(user: User, settings) -> None:
    from apps.characters.models import ImgGenLog

    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )
    log = ImgGenLog.objects.create(user=user, gen_cnt=1)

    with patch("apps.characters.tasks.httpx.post", side_effect=RuntimeError("AI down")):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(
            str(job.job_id), "몽글", "착한 곰", log.img_gen_log_id
        )

    job.refresh_from_db()
    assert job.status == "FAILED"
    # 실패했으므로 해당 생성 로그는 삭제(환불)되어야 한다.
    assert not ImgGenLog.objects.filter(pk=log.img_gen_log_id).exists()


# AI 가 생성한 성격/말투/배경이 하나의 persona 텍스트로 합쳐져 저장되는지 확인
@pytest.mark.django_db
def test_process_job_composes_persona_from_ai_result(user: User, settings) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-p"}, "error": None}
    )
    poll = _mock_response(
        {
            "status": "done",
            "result": {
                "image_url": "https://cdn/p.png",
                "appearance": "둥근 갈색 몸",
                "personality": "밝고 명랑함",
                "speech_style": "반말, 친근함",
                "background": "숲속 마을 출신",
            },
            "error": None,
        }
    )

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit),
        patch("apps.characters.tasks.httpx.get", return_value=poll),
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    job.refresh_from_db()
    assert job.persona == (
        "[성격] 밝고 명랑함\n[말투] 반말, 친근함\n[배경] 숲속 마을 출신"
    )


# compose 로 버려지는 원본(유저 입력 + LLM raw 출력)이 S3 감사 로그로 보존되는지 확인
@pytest.mark.django_db
def test_process_job_writes_generation_audit_log(user: User, settings) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-a"}, "error": None}
    )
    ai_result = {
        "image_url": "https://cdn/a.png",
        "appearance": "둥근 갈색 몸",
        "personality": "밝고 명랑함",
        "speech_style": "반말, 친근함",
        "background": "숲속 마을 출신",
    }
    poll = _mock_response({"status": "done", "result": ai_result, "error": None})

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit),
        patch("apps.characters.tasks.httpx.get", return_value=poll),
        patch("infrastructure.storage.s3.put_json") as mock_put,
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    assert mock_put.call_count == 1
    key, payload = mock_put.call_args.args
    assert "/log/character-gen/dt=" in f"/{key}"
    assert key.endswith(f"/{job.user_id}/{job.job_id}.json")
    # 유저 원본 입력 보존
    assert payload["input"] == {
        "name": "몽글",
        "persona": "착한 곰",
        "personality_keywords": ["다정한"],
    }
    # LLM raw 출력 보존 + 합쳐진 persona 동봉
    assert payload["ai_result"] == ai_result
    assert payload["composed_persona"] == (
        "[성격] 밝고 명랑함\n[말투] 반말, 친근함\n[배경] 숲속 마을 출신"
    )
    # 서버 end-to-end 소요시간(초) 기록
    assert isinstance(payload["server_elapsed_seconds"], int | float)
    assert payload["server_elapsed_seconds"] >= 0


# S3 감사 로그 저장이 실패해도 생성 잡은 계속 진행(SUCCEEDED)되는지 확인
@pytest.mark.django_db
def test_process_job_succeeds_when_audit_log_fails(user: User, settings) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-f"}, "error": None}
    )
    poll = _mock_response(
        {
            "status": "done",
            "result": {"image_url": "https://cdn/f.png", "appearance": "둥근 갈색 몸"},
            "error": None,
        }
    )

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit),
        patch("apps.characters.tasks.httpx.get", return_value=poll),
        patch(
            "infrastructure.storage.s3.put_json",
            side_effect=RuntimeError("S3 down"),
        ),
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    job.refresh_from_db()
    assert job.status == "SUCCEEDED"


# 이미지까지: source_image 가 있으면 payload 에 source_image_key/content_type/url 이 채워지는지 확인
@override_settings(AWS_S3_BUCKET="test-bucket", AWS_S3_REGION="ap-northeast-2")
@pytest.mark.django_db
def test_process_job_with_source_image_passes_url(user: User, settings) -> None:
    from apps.characters.models import SourceImage

    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    source = SourceImage.objects.create(
        user=user,
        object_key="source-images/u1/abc.png",
        content_type="image/png",
        status=SourceImage.Status.UPLOAD_COMPLETED,
        expires_at=timezone.now(),
    )
    job = CharacterGenerationJob.objects.create(
        user=user,
        source_image=source,
        personality_keywords=["다정한"],
        status="QUEUED",
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-2"}, "error": None}
    )
    poll = _mock_response(
        {
            "status": "done",
            "result": {"image_url": "https://cdn/y.png", "appearance": "빨간 리본"},
            "error": None,
        }
    )

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit) as mock_post,
        patch("apps.characters.tasks.httpx.get", return_value=poll),
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    sent = mock_post.call_args.kwargs["json"]
    assert sent["source_image_key"] == "source-images/u1/abc.png"
    assert sent["source_image_content_type"] == "image/png"
    assert (
        sent["source_image_url"]
        == "https://test-bucket.s3.ap-northeast-2.amazonaws.com/source-images/u1/abc.png"
    )
    job.refresh_from_db()
    assert job.status == "SUCCEEDED"
    assert job.appearance == "빨간 리본"


# 폴링이 error 를 반환하면 job 이 FAILED 로 기록되는지 확인
@pytest.mark.django_db
def test_process_job_poll_error_marks_failed(user: User, settings) -> None:
    settings.AI_SERVICE_URL = "http://ai.test"
    settings.AI_SERVICE_TOKEN = "secret-key"  # noqa: S105
    job = CharacterGenerationJob.objects.create(
        user=user, personality_keywords=["다정한"], status="QUEUED"
    )

    submit = _mock_response(
        {"status": "pending", "result": {"job_id": "ai-3"}, "error": None}
    )
    poll = _mock_response(
        {
            "status": "error",
            "result": None,
            "error": {"code": "character_generation_failed", "message": "boom"},
        }
    )

    with (
        patch("apps.characters.tasks.httpx.post", return_value=submit),
        patch("apps.characters.tasks.httpx.get", return_value=poll),
    ):
        from apps.characters.tasks import process_character_generation_job

        process_character_generation_job(str(job.job_id), "몽글", "착한 곰")

    job.refresh_from_db()
    assert job.status == "FAILED"


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
