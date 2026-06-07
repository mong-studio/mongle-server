"""Common pytest fixtures."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.characters.models import Character
from apps.posts.models import Post
from apps.quests.models import Quest
from apps.todos.models import Tag, Todo
from apps.users.models import User


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email="test@test.com",
        password="password123",
        user_name="테스터",
    )


@pytest.fixture
def auth_client(user: User) -> APIClient:
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.fixture
def tag(db) -> Tag:
    return Tag.objects.create(tag_id=1, content="공부", color="#ff0000")


@pytest.fixture
def character(db, user: User) -> Character:
    return Character.objects.create(
        user=user,
        character_name="테스트캐릭터",
        gen_img_url="https://example.com/img.png",
        persona="테스트 페르소나",
    )


@pytest.fixture
def todo(db, user: User, tag: Tag) -> Todo:
    return Todo.objects.create(
        user=user,
        tag=tag,
        content="테스트TODO",
        todo_date="2026-06-02",
    )


@pytest.fixture
def quest(db, character: Character, todo: Todo) -> Quest:
    return Quest.objects.create(
        character=character,
        todo=todo,
        content="테스트 퀘스트",
    )


@pytest.fixture
def post(db, character: Character, quest: Quest) -> Post:
    return Post.objects.create(
        character=character,
        quest=quest,
        content="테스트 게시글",
        img_url="https://example.com/img.png",
    )
