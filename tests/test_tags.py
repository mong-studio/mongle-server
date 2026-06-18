"""유저 태그 CRUD 엔드포인트 테스트 (/api/v1/tags/).

캘린더에서 만든 태그가 즉시 보이지 않던 버그: 백엔드가 생성/수정/삭제를
지원하지 않아 POST가 실패했었다. 생성이 201로 태그를 돌려주고 본인 것만
조회되는지 검증한다.
"""

from __future__ import annotations

import pytest

from apps.tags.models import Tag
from apps.todos.models import Todo
from apps.users.models import User


@pytest.mark.django_db
def test_create_tag_returns_created_tag(auth_client) -> None:
    response = auth_client.post(
        "/api/v1/tags/",
        data={"content": "운동", "color": "#62a256"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "운동"
    assert body["color"] == "#62a256"
    assert isinstance(body["tag_id"], int)
    assert Tag.objects.filter(content="운동").exists()


@pytest.mark.django_db
def test_list_returns_only_own_tags(auth_client, user: User, tag: Tag) -> None:
    other = User.objects.create_user(
        email="other@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    Tag.objects.create(user=other, content="남의태그", color="#000000")

    response = auth_client.get("/api/v1/tags/")

    assert response.status_code == 200
    contents = {t["content"] for t in response.json()}
    assert tag.content in contents
    assert "남의태그" not in contents


@pytest.mark.django_db
def test_update_and_delete_tag(auth_client, tag: Tag) -> None:
    patch = auth_client.patch(
        f"/api/v1/tags/{tag.tag_id}/",
        data={"content": "수정됨", "color": "#123456"},
        content_type="application/json",
    )
    assert patch.status_code == 200
    assert patch.json()["content"] == "수정됨"

    delete = auth_client.delete(f"/api/v1/tags/{tag.tag_id}/")
    assert delete.status_code == 204
    assert not Tag.objects.filter(tag_id=tag.tag_id).exists()


@pytest.mark.django_db
def test_cannot_touch_other_users_tag(auth_client) -> None:
    other = User.objects.create_user(
        email="other2@test.com",
        password="password123",
        user_name="남2",
        birth="2000-01-01",
    )
    foreign = Tag.objects.create(user=other, content="외부", color="#abcdef")

    response = auth_client.delete(f"/api/v1/tags/{foreign.tag_id}/")

    assert response.status_code == 404
    assert Tag.objects.filter(tag_id=foreign.tag_id).exists()


@pytest.mark.django_db
def test_delete_tag_in_use_returns_409(auth_client, tag: Tag, todo: Todo) -> None:
    # todo 픽스처가 tag를 참조(PROTECT)하므로 삭제가 막혀야 한다.
    response = auth_client.delete(f"/api/v1/tags/{tag.tag_id}/")

    assert response.status_code == 409
    assert response.json()["error"] == "TAG_IN_USE"
    assert Tag.objects.filter(tag_id=tag.tag_id).exists()
