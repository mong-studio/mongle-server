"""Todos AI bridge tests."""

from __future__ import annotations

from datetime import timedelta
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


# TODO 생성 AI 호출 실패 시 가짜 후보 없이 502 가 반환되는지 확인
@pytest.mark.django_db
def test_todo_generate_returns_502_when_ai_fails(auth_client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate.side_effect = TodoAIClientError("down")

        response = auth_client.post(
            "/api/v1/todos/generate/",
            data={"prompt": "운동하고 빨래하고 Django 공부"},
            content_type="application/json",
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_SERVICE_UNAVAILABLE"


# 인증된 사용자가 TODO 채팅 AI 엔드포인트에서 후속 질문을 받을 수 있는지 확인
@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_chat_returns_follow_up_for_authenticated_user(auth_client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.submit_chat.return_value = "job-123"

        response = auth_client.post(
            "/api/v1/todos/chat/",
            data={"message": "시험 공부 해야 해", "thread_id": None},
            content_type="application/json",
        )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["result"]["job_id"] == "job-123"
    factory.return_value.submit_chat.assert_called_once()


@pytest.mark.django_db
@override_settings(MONGLE_AI_API_KEY=TEST_INTERNAL_TOKEN)
def test_todo_chat_job_poll_returns_ai_envelope(auth_client) -> None:
    job_id = "11111111111111111111111111111111"
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.poll_chat.return_value = {
            "status": "done",
            "result": {
                "kind": "follow_up",
                "thread_id": "thread-2",
                "question": "언제까지 끝내고 싶으세요?",
                "missing_aspects": ["deadline"],
            },
            "error": None,
        }

        response = auth_client.get(f"/api/v1/todos/chat/{job_id}/")

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["result"]["kind"] == "follow_up"
    factory.return_value.poll_chat.assert_called_once_with(job_id=job_id)


@pytest.mark.django_db
def test_todo_planner_confirm_persists_todos_and_schedules(
    auth_client, character
) -> None:
    today = timezone.localdate().isoformat()
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.return_value = {
            "generated": [],
            "skipped": [],
        }

        response = auth_client.post(
            "/api/v1/todos/planner-confirm/",
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
def test_todo_planner_confirm_routes_items_by_due_date(auth_client, character) -> None:
    today = timezone.localdate()
    tomorrow = today + timezone.timedelta(days=1)

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.return_value = {
            "generated": [],
            "skipped": [],
        }

        response = auth_client.post(
            "/api/v1/todos/planner-confirm/",
            data={
                "todos": [
                    {
                        "title": "내일 발표 자료 정리",
                        "due_date": tomorrow.isoformat(),
                        "tags": ["업무"],
                    }
                ],
                "calendar_events": [
                    {
                        "title": "오늘 정처기 오답 복습",
                        "due_date": today.isoformat(),
                        "tags": ["공부"],
                    }
                ],
            },
            content_type="application/json",
        )

    assert response.status_code == 201
    assert Todo.objects.filter(
        content="오늘 정처기 오답 복습", todo_date=today
    ).exists()
    assert Schedule.objects.filter(
        title="내일 발표 자료 정리",
        start_date=tomorrow,
        end_date=tomorrow,
    ).exists()
    assert response.json()["todos"][0]["content"] == "오늘 정처기 오답 복습"
    assert response.json()["calendar_events"][0]["title"] == "내일 발표 자료 정리"
    factory.return_value.generate_quests.assert_called_once()


@pytest.mark.django_db
def test_todo_planner_confirm_requires_authentication(client) -> None:
    today = timezone.localdate().isoformat()

    response = client.post(
        "/api/v1/todos/planner-confirm/",
        data={
            "todos": [{"title": "헬스 30분", "due_date": today, "tags": ["건강"]}],
            "calendar_events": [],
        },
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_todo_planner_confirm_creates_quest_when_ai_returns_mapping(
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
            "/api/v1/todos/planner-confirm/",
            data={
                "todos": [{"title": "산책", "due_date": today, "tags": ["건강"]}],
                "calendar_events": [],
            },
            content_type="application/json",
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


# 퀘스트 미리보기 AI 호출 실패 시 가짜 퀘스트 없이 빈 결과로 degrade 되는지 확인
@pytest.mark.django_db
def test_todo_quest_preview_returns_empty_when_ai_fails(auth_client, character) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = TodoAIClientError("down")

        response = auth_client.post(
            "/api/v1/todos/quest-preview/",
            data={"todos": [{"content": "운동하기", "tags": ["건강"]}]},
            content_type="application/json",
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quest_distribution_triggered"] is False
    assert body["todos"][0]["quest"] is None


# 퀘스트 AI가 실패해도 TODO 저장은 성공하되, 가짜 퀘스트 없이 퀘스트만 생략되는지 확인
@pytest.mark.django_db
def test_todo_confirm_saves_todo_without_quest_when_quest_ai_fails(
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
    assert Quest.objects.count() == 0
    assert response.json()["quest_distribution_triggered"] is False
    assert response.json()["todos"][0]["quest"] is None


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
    """quest 분배는 generate/chat 과 동일하게 submit(202)+poll 비동기 경로를 쓴다."""
    seen = {}

    def _fake_submit_and_poll(self, *, submit_path, poll_prefix, payload):
        seen["submit_path"] = submit_path
        seen["poll_prefix"] = poll_prefix
        seen["payload"] = payload
        return {"generated": [], "skipped": []}

    monkeypatch.setattr(TodoAIClient, "_submit_and_poll", _fake_submit_and_poll)

    client = TodoAIClient(base_url="http://ai.test", api_key="token")
    result = client.generate_quests(
        todos=[{"todo_id": "todo-1"}],
        characters=[{"character_id": "char-1", "name": "몽글", "persona": "밝음"}],
        remaining_daily_quota=1,
    )

    assert result == {"generated": [], "skipped": []}
    assert seen["submit_path"] == "/v1/quest/generate"
    assert seen["poll_prefix"] == "/v1/quest/generate"


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


# 날짜가 바뀌어 todo_date 가 오늘이 된(퀘스트 없는) TODO 에 sync 가 기존 배정 로직으로 퀘스트를 채우는지 확인
@pytest.mark.django_db
def test_sync_quests_assigns_quest_to_todays_questless_todo(
    auth_client, user, character, tag
) -> None:
    today = timezone.localdate()
    todo = Todo.objects.create(user=user, tag=tag, content="토익 공부", todo_date=today)

    def _fake_generate_quests(*, todos, characters, remaining_daily_quota):
        return {
            "generated": [
                {
                    "todo_id": todos[0]["todo_id"],
                    "character_id": characters[0]["character_id"],
                    "quest_text": "단어 30개 외우기",
                }
            ],
            "skipped": [],
        }

    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate_quests.side_effect = _fake_generate_quests
        response = auth_client.post(
            "/api/v1/todos/sync-quests/", data={}, content_type="application/json"
        )

    assert response.status_code == 200
    assert Quest.objects.filter(todo=todo).count() == 1
    body = response.json()
    assert body["quest_distribution_triggered"] is True
    assert body["todos"][0]["quest"]["content"] == "단어 30개 외우기"


# 아직 미래 날짜인 TODO 는 sync 대상이 아니며(당일만 부여) AI 도 호출하지 않는지 확인
@pytest.mark.django_db
def test_sync_quests_ignores_future_dated_todo(
    auth_client, user, character, tag
) -> None:
    tomorrow = timezone.localdate() + timedelta(days=1)
    Todo.objects.create(user=user, tag=tag, content="미래 할 일", todo_date=tomorrow)

    with patch("apps.todos.views._todo_ai_client") as factory:
        response = auth_client.post(
            "/api/v1/todos/sync-quests/", data={}, content_type="application/json"
        )

    assert response.status_code == 200
    assert Quest.objects.count() == 0
    factory.return_value.generate_quests.assert_not_called()
