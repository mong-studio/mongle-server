"""Todos AI bridge tests."""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
import pytest

from apps.quests.models import Quest
from apps.todos.ai_client import TodoAIClient, TodoAIClientError
from apps.todos.models import Schedule, Todo

TEST_INTERNAL_TOKEN = "test-internal-token"  # noqa: S105 - test-only token


# 인증된 사용자가 TODO 생성 AI 엔드포인트를 호출할 수 있는지 확인
@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_generate_works_for_authenticated_user(auth_client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate.return_value = {
            "kind": "candidates",
            "thread_id": "thread-1",
            "todos": [{"title": "운동", "due_date": "2026-06-08", "tags": ["건강"]}],
            "calendar_events": [],
            "summary_text": None,
        }

        response = auth_client.post(
            "/api/v1/todos/generate/",
            data={"prompt": "운동 계획"},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["thread_id"] == "thread-1"
    factory.return_value.generate.assert_called_once()


# 비로그인 사용자의 TODO 생성 AI 요청이 거부되는지 확인
@pytest.mark.django_db
def test_todo_generate_requires_authentication(client) -> None:
    response = client.post(
        "/api/v1/todos/generate/",
        data={"prompt": "운동 계획"},
        content_type="application/json",
    )

    assert response.status_code == 401


# TODO 생성 AI 호출 실패 시 로컬 fallback 후보가 반환되는지 확인
@pytest.mark.django_db
def test_todo_generate_returns_fallback_when_ai_fails(auth_client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate.side_effect = TodoAIClientError("down")

        response = auth_client.post(
            "/api/v1/todos/generate/",
            data={"prompt": "운동하고 빨래하고 Django 공부"},
            content_type="application/json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "candidates"
    assert [item["title"] for item in body["todos"]] == ["운동", "빨래", "Django 공부"]
    assert [item["tags"][0] for item in body["todos"]] == ["건강", "집안일", "공부"]


# 인증된 사용자가 TODO 채팅 AI 엔드포인트에서 후속 질문을 받을 수 있는지 확인
@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_chat_returns_follow_up_for_authenticated_user(auth_client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.chat.return_value = {
            "kind": "follow_up",
            "thread_id": "thread-2",
            "question": "언제까지 끝내고 싶으세요?",
            "missing_aspects": ["deadline"],
        }

        response = auth_client.post(
            "/api/v1/todos/chat/",
            data={"message": "시험 공부 해야 해", "thread_id": None},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "follow_up"
    assert response.json()["thread_id"] == "thread-2"


@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_commit_persists_todos_and_schedules(auth_client, character) -> None:
    today = timezone.localdate().isoformat()
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.return_value = {
            "generated": [],
            "skipped": [],
        }

        response = auth_client.post(
            "/api/v1/todos/commit/",
            data={
                "todos": [{"title": "헬스 30분", "due_date": today, "tags": ["건강"]}],
                "calendar_events": [
                    {
                        "title": "프로젝트 발표",
                        "due_date": "2026-06-10",
                        "tags": ["업무"],
                    }
                ],
            },
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_TOKEN=TEST_INTERNAL_TOKEN,
        )

    assert response.status_code == 201
    assert Todo.objects.count() == 1
    assert Schedule.objects.count() == 1
    assert Todo.objects.filter(tag__content="건강").exists()
    assert Schedule.objects.filter(tag__content="업무").exists()
    assert response.json()["todos"][0]["content"] == "헬스 30분"
    assert response.json()["calendar_events"][0]["title"] == "프로젝트 발표"
    factory.return_value.generate_quests.assert_called_once()


@pytest.mark.django_db
def test_todo_commit_rejects_missing_internal_token(auth_client) -> None:
    today = timezone.localdate().isoformat()

    response = auth_client.post(
        "/api/v1/todos/commit/",
        data={
            "todos": [{"title": "헬스 30분", "due_date": today, "tags": ["건강"]}],
            "calendar_events": [],
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_commit_creates_quest_when_ai_returns_mapping(
    auth_client, character
) -> None:
    today = timezone.localdate().isoformat()

    def _fake_generate_quests(*, todos, characters, remaining_daily_quota):
        return {
            "generated": [
                {
                    "todo_id": todos[0]["todo_id"],
                    "character_id": characters[0]["character_id"],
                    "quest_text": "마을 광장 한 바퀴 돌기",
                }
            ],
            "skipped": [],
        }

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = _fake_generate_quests

        response = auth_client.post(
            "/api/v1/todos/commit/",
            data={
                "todos": [{"title": "산책", "due_date": today, "tags": ["건강"]}],
                "calendar_events": [],
            },
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_TOKEN=TEST_INTERNAL_TOKEN,
        )

    assert response.status_code == 201
    assert Quest.objects.count() == 1
    assert response.json()["quest_distribution_triggered"] is True
    assert response.json()["todos"][0]["quest"]["content"] == "마을 광장 한 바퀴 돌기"


# 확정 저장 엔드포인트가 TODO를 만들고 AI 매핑 결과로 퀘스트까지 생성하는지 확인
@pytest.mark.django_db
def test_todo_confirm_creates_quest_when_ai_returns_mapping(
    auth_client, character, tag
) -> None:
    today = timezone.localdate().isoformat()

    def _fake_generate_quests(*, todos, characters, remaining_daily_quota):
        return {
            "generated": [
                {
                    "todo_id": todos[0]["todo_id"],
                    "character_id": characters[0]["character_id"],
                    "quest_text": "구름 정원 물 주기",
                }
            ],
            "skipped": [],
        }

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = _fake_generate_quests

        response = auth_client.post(
            "/api/v1/todos/confirm/",
            data={
                "todos": [
                    {
                        "content": "화분 돌보기",
                        "todo_date": today,
                        "tag_id": tag.tag_id,
                    }
                ]
            },
            content_type="application/json",
        )

    assert response.status_code == 201
    assert Todo.objects.filter(content="화분 돌보기").exists()
    assert Quest.objects.count() == 1
    body = response.json()
    assert body["quest_distribution_triggered"] is True
    assert body["todos"][0]["quest"]["content"] == "구름 정원 물 주기"
    factory.return_value.generate_quests.assert_called_once()


# 퀘스트 미리보기에서 기존 일일 퀘스트 수를 반영해 캐릭터 퀘스트를 반환하는지 확인
@pytest.mark.django_db
def test_todo_quest_preview_returns_character_quest(auth_client, character) -> None:
    today = timezone.localdate()
    existing_todo = Todo.objects.create(
        user=character.user,
        tag=character.user.tags.create(content="기존", color="#FFFFFF"),
        content="기존 할 일",
        todo_date=today,
    )
    Quest.objects.create(
        character=character,
        todo=existing_todo,
        content="이미 있던 퀘스트",
    )

    def _fake_generate_quests(*, todos, characters, remaining_daily_quota):
        assert remaining_daily_quota == 1
        return {
            "generated": [
                {
                    "todo_id": todos[0]["todo_id"],
                    "character_id": characters[0]["character_id"],
                    "quest_text": "토끼뜰에서 공식 세 줄 외우기",
                }
            ],
            "skipped": [],
        }

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = _fake_generate_quests

        response = auth_client.post(
            "/api/v1/todos/quest-preview/",
            data={"todos": [{"content": "공부하기", "tags": ["공부"]}]},
            content_type="application/json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quest_distribution_triggered"] is True
    assert body["todos"][0]["content"] == "공부하기"
    assert body["todos"][0]["quest"] == {
        "content": "토끼뜰에서 공식 세 줄 외우기",
        "character_id": str(character.character_id),
        "character_name": character.character_name,
        "character_image_url": character.gen_img_url,
    }


# 퀘스트 미리보기 AI 호출 실패 시 기본 퀘스트 문구로 fallback 되는지 확인
@pytest.mark.django_db
def test_todo_quest_preview_returns_fallback_when_ai_fails(
    auth_client, character
) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = TodoAIClientError("down")

        response = auth_client.post(
            "/api/v1/todos/quest-preview/",
            data={"todos": [{"content": "운동하기", "tags": ["건강"]}]},
            content_type="application/json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quest_distribution_triggered"] is True
    assert body["todos"][0]["quest"]["character_id"] == str(character.character_id)
    assert body["todos"][0]["quest"]["character_name"] == character.character_name
    assert body["todos"][0]["quest"]["content"] == (
        f"{character.character_name}가 몽글 구름에 리본 달아주기"
    )


# 퀘스트 AI가 실패해도 TODO 저장은 성공하고 기본 퀘스트가 생성되는지 확인
@pytest.mark.django_db
def test_todo_confirm_saves_todo_when_quest_ai_fails(
    auth_client, character, tag
) -> None:
    today = timezone.localdate().isoformat()

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = TodoAIClientError("boom")

        response = auth_client.post(
            "/api/v1/todos/confirm/",
            data={
                "todos": [
                    {
                        "content": "물 마시기",
                        "todo_date": today,
                        "tag_id": tag.tag_id,
                    }
                ]
            },
            content_type="application/json",
        )

    assert response.status_code == 201
    assert Todo.objects.filter(content="물 마시기").exists()
    assert Quest.objects.count() == 1
    assert response.json()["quest_distribution_triggered"] is True
    assert (
        response.json()["todos"][0]["quest"]["character_name"]
        == character.character_name
    )
    assert response.json()["todos"][0]["quest"]["content"] == (
        f"{character.character_name}가 몽글 구름에 리본 달아주기"
    )


# 확정 저장 요청에서 tag_id 대신 태그 이름 배열을 받아 태그를 연결하는지 확인
@pytest.mark.django_db
def test_todo_confirm_accepts_tag_names(auth_client, character) -> None:
    today = timezone.localdate().isoformat()

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.return_value = {
            "generated": [],
            "skipped": [],
        }

        response = auth_client.post(
            "/api/v1/todos/confirm/",
            data={
                "todos": [
                    {
                        "content": "명상하기",
                        "todo_date": today,
                        "tags": ["건강"],
                    }
                ]
            },
            content_type="application/json",
        )

    assert response.status_code == 201
    todo = Todo.objects.get(content="명상하기")
    assert todo.tag.content == "건강"
    assert response.json()["todos"][0]["tags"] == ["건강"]


# 퀘스트 생성 클라이언트가 FastAPI의 퀘스트 생성 경로로 요청을 보내는지 확인
def test_todo_ai_client_uses_fastapi_quest_path(monkeypatch) -> None:
    seen = {}

    def _fake_post(self, path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return {"generated": [], "skipped": []}

    monkeypatch.setattr(TodoAIClient, "_post", _fake_post)

    client = TodoAIClient(base_url="http://ai.test", api_key="token")
    result = client.generate_quests(
        todos=[{"todo_id": "todo-1"}],
        characters=[{"character_id": "char-1", "name": "몽글", "persona": "밝음"}],
        remaining_daily_quota=1,
    )

    assert result == {"generated": [], "skipped": []}
    assert seen["path"] == "/v1/quest/generate"


# TODO AI 클라이언트가 캐릭터 생성 경로와 동일하게 httpx 기반 요청을 사용하는지 확인
def test_todo_ai_client_request_uses_httpx_with_internal_headers() -> None:
    with patch("apps.todos.ai_client.httpx.request") as request_mock:
        request_mock.return_value.json.return_value = {
            "status": "done",
            "result": {"ok": True},
        }
        request_mock.return_value.raise_for_status.return_value = None

        client = TodoAIClient(base_url="https://ai.test/", api_key="token")
        result = client._request(
            "POST", "/v1/probe", payload={"hello": "world"}, timeout=7
        )

    assert result == {"status": "done", "result": {"ok": True}}
    request_mock.assert_called_once()
    _, url = request_mock.call_args.args
    kwargs = request_mock.call_args.kwargs
    assert url == "https://ai.test/v1/probe"
    assert kwargs["json"] == {"hello": "world"}
    assert kwargs["timeout"] == 7
    assert kwargs["headers"]["X-API-Key"] == "token"
    assert kwargs["headers"]["X-Internal-Service-Token"] == "token"


def test_todo_ai_client_request_maps_http_status_errors() -> None:
    import httpx

    request = httpx.Request("POST", "https://ai.test/v1/probe")
    response = httpx.Response(403, text="error code: 1010", request=request)

    with patch("apps.todos.ai_client.httpx.request") as request_mock:
        request_mock.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=request,
            response=response,
        )

        client = TodoAIClient(base_url="https://ai.test", api_key="token")
        with pytest.raises(TodoAIClientError, match="mongle-ai HTTP 403"):
            client._request("POST", "/v1/probe", payload={})
