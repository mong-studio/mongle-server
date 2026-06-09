"""Todos AI bridge tests."""

from __future__ import annotations

from unittest.mock import patch

from django.utils import timezone
import pytest

from apps.quests.models import Quest
from apps.todos.models import Schedule, Tag, Todo


@pytest.mark.django_db
def test_todo_generate_bridge_works_without_auth(client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.generate.return_value = {
            "kind": "candidates",
            "thread_id": "thread-1",
            "todos": [{"title": "운동", "due_date": "2026-06-08", "tags": ["건강"]}],
            "calendar_events": [],
            "summary_text": None,
        }

        response = client.post(
            "/api/v1/todos/generate/",
            data={"prompt": "운동 계획"},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["thread_id"] == "thread-1"
    factory.return_value.generate.assert_called_once()


@pytest.mark.django_db
def test_todo_chat_bridge_returns_follow_up(client) -> None:
    with patch("apps.todos.views._todo_ai_client") as factory:
        factory.return_value.chat.return_value = {
            "kind": "follow_up",
            "thread_id": "thread-2",
            "question": "언제까지 끝내고 싶으세요?",
            "missing_aspects": ["deadline"],
        }

        response = client.post(
            "/api/v1/todos/chat/",
            data={"message": "시험 공부 해야 해", "thread_id": None},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "follow_up"
    assert response.json()["thread_id"] == "thread-2"


@pytest.mark.django_db
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
        )

    assert response.status_code == 201
    assert Todo.objects.count() == 1
    assert Schedule.objects.count() == 1
    assert Tag.objects.count() == 2
    assert response.json()["todos"][0]["content"] == "헬스 30분"
    assert response.json()["calendar_events"][0]["title"] == "프로젝트 발표"
    factory.return_value.generate_quests.assert_called_once()


@pytest.mark.django_db
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
        )

    assert response.status_code == 201
    assert Quest.objects.count() == 1
    assert response.json()["quest_distribution_triggered"] is True
    assert response.json()["todos"][0]["quest"]["content"] == "마을 광장 한 바퀴 돌기"
