"""Posts 앱 테스트 - 게시글 목록/상세, 댓글 생성"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character
from apps.posts.models import Comment, Post, Reply
from apps.posts.tasks import generate_character_reply
from apps.quests.models import Quest
from apps.users.models import User


# 비로그인 상태에서 게시글 목록 조회 시 401 반환 확인
@pytest.mark.django_db
def test_post_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/posts/")
    assert response.status_code == 401


# 게시글이 없을 때 빈 배열 반환 확인
@pytest.mark.django_db
def test_post_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    assert response.json() == []


# 게시글 목록에 content·img_url·comments 필드가 포함되는지 확인
# PostSerializer 필드명(img_url, content)이 모델과 일치하는지 검증
# 이전에 image_url/caption 으로 잘못 선언되어 500이 났던 회귀 방지용 테스트
@pytest.mark.django_db
def test_post_list_returns_posts(auth_client: APIClient, post: Post) -> None:
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["content"] == "테스트 게시글"
    assert data[0]["img_url"] == "https://example.com/img.png"
    assert "comments" in data[0]


# 다른 사용자 캐릭터의 게시글은 내 피드 목록에 노출되지 않아야 함 (회귀 방지)
@pytest.mark.django_db
def test_post_list_excludes_other_users(auth_client: APIClient, quest: Quest) -> None:
    other_user = User.objects.create_user(
        email="other@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    other_char = Character.objects.create(
        user=other_user,
        character_name="남캐릭터",
        gen_img_url="https://example.com/other.png",
        persona="남 페르소나",
    )
    Post.objects.create(
        character=other_char,
        quest=quest,
        content="남의 게시글",
        img_url="https://example.com/other.png",
    )
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    assert response.json() == []


# 다른 사용자 캐릭터의 게시글 상세는 404 (소유권 스코프)
@pytest.mark.django_db
def test_post_detail_other_user_not_found(auth_client: APIClient, quest: Quest) -> None:
    other_user = User.objects.create_user(
        email="other2@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    other_char = Character.objects.create(
        user=other_user,
        character_name="남캐릭터",
        gen_img_url="https://example.com/other.png",
        persona="남 페르소나",
    )
    other_post = Post.objects.create(
        character=other_char,
        quest=quest,
        content="남의 게시글",
        img_url="https://example.com/other.png",
    )
    response = auth_client.get(f"/api/v1/posts/{other_post.post_id}/")
    assert response.status_code == 404


# 비활성(은퇴) 캐릭터의 게시물도 내 피드에 노출되며, character_is_active=False 로 표시됨
@pytest.mark.django_db
def test_post_list_includes_inactive_marked(
    auth_client: APIClient, user: User, quest: Quest
) -> None:
    retired = Character.objects.create(
        user=user,
        character_name="은퇴캐릭터",
        gen_img_url="https://example.com/old.png",
        persona="옛 페르소나",
        is_active=False,
    )
    Post.objects.create(
        character=retired,
        quest=quest,
        content="옛 게시글",
        img_url="https://example.com/old.png",
    )
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["content"] == "옛 게시글"
    assert data[0]["character_is_active"] is False


# 비로그인 상태에서 게시글 상세 조회 시 401 반환 확인
@pytest.mark.django_db
def test_post_detail_unauthenticated(post: Post) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/posts/{post.post_id}/")
    assert response.status_code == 401


# 게시글 상세 조회 성공 시 content 필드가 올바른지 확인
@pytest.mark.django_db
def test_post_detail_authenticated(auth_client: APIClient, post: Post) -> None:
    response = auth_client.get(f"/api/v1/posts/{post.post_id}/")
    assert response.status_code == 200
    assert response.json()["content"] == "테스트 게시글"


# 존재하지 않는 post_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_post_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/posts/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404


# 좋아요 토글: 두 번 호출하면 on→off 로 DB에 저장됨
@pytest.mark.django_db
def test_post_like_toggle_persists(auth_client: APIClient, post: Post) -> None:
    res1 = auth_client.post(f"/api/v1/posts/{post.post_id}/like/")
    assert res1.status_code == 200
    assert res1.json()["is_liked"] is True
    post.refresh_from_db()
    assert post.is_liked is True

    res2 = auth_client.post(f"/api/v1/posts/{post.post_id}/like/")
    assert res2.json()["is_liked"] is False
    post.refresh_from_db()
    assert post.is_liked is False


# 다른 사용자 캐릭터의 게시물은 좋아요 불가 (404)
@pytest.mark.django_db
def test_post_like_other_user_not_found(auth_client: APIClient, quest: Quest) -> None:
    other_user = User.objects.create_user(
        email="other3@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    other_char = Character.objects.create(
        user=other_user,
        character_name="남캐릭터",
        gen_img_url="https://example.com/other.png",
        persona="남 페르소나",
    )
    other_post = Post.objects.create(
        character=other_char,
        quest=quest,
        content="남의 게시글",
        img_url="https://example.com/other.png",
    )
    response = auth_client.post(f"/api/v1/posts/{other_post.post_id}/like/")
    assert response.status_code == 404
    other_post.refresh_from_db()
    assert other_post.is_liked is False


# 비로그인 상태에서 댓글 작성 시 401 반환 확인
@pytest.mark.django_db
def test_comment_create_unauthenticated(post: Post) -> None:
    client = APIClient()
    response = client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글 내용"},
        format="json",
    )
    assert response.status_code == 401


# 댓글 작성 성공 시 201 반환 및 content 필드 확인
@pytest.mark.django_db
def test_comment_create_success(auth_client: APIClient, post: Post) -> None:
    response = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글 내용"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["content"] == "댓글 내용"


# 다른 사용자 캐릭터의 게시물에는 댓글 작성 불가 (404)
@pytest.mark.django_db
def test_comment_create_other_user_not_found(
    auth_client: APIClient, quest: Quest
) -> None:
    other_user = User.objects.create_user(
        email="other4@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    other_char = Character.objects.create(
        user=other_user,
        character_name="남캐릭터",
        gen_img_url="https://example.com/other.png",
        persona="남 페르소나",
    )
    other_post = Post.objects.create(
        character=other_char,
        quest=quest,
        content="남의 게시글",
        img_url="https://example.com/other.png",
    )
    response = auth_client.post(
        f"/api/v1/posts/{other_post.post_id}/comments/",
        {"content": "댓글"},
        format="json",
    )
    assert response.status_code == 404


# 존재하지 않는 게시글에 댓글 작성 시 404 반환 확인
@pytest.mark.django_db
def test_comment_create_post_not_found(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/posts/00000000-0000-0000-0000-000000000000/comments/",
        {"content": "댓글"},
        format="json",
    )
    assert response.status_code == 404


# 비활성 캐릭터는 답글(Reply)을 생성하지 않는다 (AI 호출 전 조기 종료)
@pytest.mark.django_db
def test_inactive_character_skips_reply(
    user: User, post: Post, character: Character
) -> None:
    character.is_active = False
    character.save(update_fields=["is_active"])
    comment = Comment.objects.create(post=post, user=user, content="안녕")

    generate_character_reply(str(comment.comment_id))

    assert not Reply.objects.filter(comment=comment).exists()
