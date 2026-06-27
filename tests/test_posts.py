"""Posts 앱 테스트 - 게시글 목록/상세, 댓글 생성"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.characters.models import Character
from apps.posts.models import Comment, Post, Reply
from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.models import Todo
from apps.users.models import TokenTransaction, User


def _make_other_user_post() -> Post:
    """다른 사용자 소유의 게시글을 하나 만든다(스코프 격리 검증용)."""
    other = User.objects.create_user(
        email="other@test.com",
        password="password123",
        user_name="다른유저",
        birth="2000-01-01",
    )
    character = Character.objects.create(
        user=other,
        character_name="남의캐릭터",
        gen_img_url="https://example.com/other.png",
        persona="페르소나",
    )
    tag = Tag.objects.create(tag_id=2, user=other, content="운동", color="#00ff00")
    todo = Todo.objects.create(
        user=other, tag=tag, content="남의TODO", todo_date="2026-06-02"
    )
    quest = Quest.objects.create(character=character, todo=todo, content="남의 퀘스트")
    return Post.objects.create(
        character=character,
        quest=quest,
        content="남의 게시글",
        img_url="https://example.com/other.png",
    )


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


# 목록에는 본인 캐릭터의 게시글만 보이고 다른 사용자의 게시글은 제외된다
@pytest.mark.django_db
def test_post_list_only_returns_own_posts(auth_client: APIClient, post: Post) -> None:
    other_post = _make_other_user_post()
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    data = response.json()
    post_ids = {item["post_id"] for item in data}
    assert str(post.post_id) in post_ids
    assert str(other_post.post_id) not in post_ids


# 다른 사용자의 게시글 상세를 post_id로 직접 조회하면 404 (IDOR 방지)
@pytest.mark.django_db
def test_post_detail_other_user_forbidden(auth_client: APIClient) -> None:
    other_post = _make_other_user_post()
    response = auth_client.get(f"/api/v1/posts/{other_post.post_id}/")
    assert response.status_code == 404


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


# 본인 게시글 삭제 성공 시 204 + 게시글·댓글이 함께 삭제(CASCADE)되는지 확인
@pytest.mark.django_db
def test_post_delete_authenticated(
    auth_client: APIClient, user: User, post: Post
) -> None:
    comment = Comment.objects.create(post=post, user=user, content="댓글")

    response = auth_client.delete(f"/api/v1/posts/{post.post_id}/")

    assert response.status_code == 204
    assert not Post.objects.filter(post_id=post.post_id).exists()
    assert not Comment.objects.filter(pk=comment.pk).exists()  # CASCADE 로 함께 삭제


# 다른 사용자의 게시글은 삭제할 수 없다(404, 게시글 유지)
@pytest.mark.django_db
def test_post_delete_other_user_forbidden(auth_client: APIClient) -> None:
    other_post = _make_other_user_post()
    response = auth_client.delete(f"/api/v1/posts/{other_post.post_id}/")
    assert response.status_code == 404
    assert Post.objects.filter(post_id=other_post.post_id).exists()


# 비로그인 상태에서 삭제 시 401 반환 확인
@pytest.mark.django_db
def test_post_delete_unauthenticated(post: Post) -> None:
    response = APIClient().delete(f"/api/v1/posts/{post.post_id}/")
    assert response.status_code == 401


# 이사한 캐릭터의 게시물/답글에도 캐릭터 이미지 URL이 포함되는지 확인
@pytest.mark.django_db
def test_post_detail_includes_inactive_character_images(
    auth_client: APIClient,
    post: Post,
    character: Character,
    user: User,
) -> None:
    comment = Comment.objects.create(post=post, user=user, content="댓글")
    Reply.objects.create(comment=comment, character=character, content="답글")
    character.is_active = False
    character.save(update_fields=["is_active"])

    response = auth_client.get(f"/api/v1/posts/{post.post_id}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gen_img_url"] == "https://example.com/img.png"
    assert payload["comments"][0]["replies"][0]["gen_img_url"] == (
        "https://example.com/img.png"
    )


# 존재하지 않는 post_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_post_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/posts/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404


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


# 다른 사용자의 게시글에 댓글 작성 시 404 (완전 개인용 — IDOR 방지)
@pytest.mark.django_db
def test_comment_create_other_user_forbidden(auth_client: APIClient) -> None:
    other_post = _make_other_user_post()
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


# 좋아요 토글: 첫 호출 True, 재호출 False — DB에 저장되는지 확인
@pytest.mark.django_db
def test_post_like_toggle(auth_client: APIClient, post: Post) -> None:
    assert post.is_liked is False

    r1 = auth_client.post(f"/api/v1/posts/{post.post_id}/like/")
    assert r1.status_code == 200
    assert r1.json()["is_liked"] is True
    post.refresh_from_db()
    assert post.is_liked is True

    r2 = auth_client.post(f"/api/v1/posts/{post.post_id}/like/")
    assert r2.status_code == 200
    assert r2.json()["is_liked"] is False
    post.refresh_from_db()
    assert post.is_liked is False


# 비로그인 상태에서 좋아요 시 401 반환 확인
@pytest.mark.django_db
def test_post_like_unauthenticated(post: Post) -> None:
    client = APIClient()
    response = client.post(f"/api/v1/posts/{post.post_id}/like/")
    assert response.status_code == 401


# 다른 사용자의 게시글에 좋아요 시 404 (완전 개인용 — IDOR 방지)
@pytest.mark.django_db
def test_post_like_other_user_forbidden(auth_client: APIClient) -> None:
    other_post = _make_other_user_post()
    response = auth_client.post(f"/api/v1/posts/{other_post.post_id}/like/")
    assert response.status_code == 404


# 목록 응답에 is_liked 필드가 포함되는지 확인
@pytest.mark.django_db
def test_post_list_includes_is_liked(auth_client: APIClient, post: Post) -> None:
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    assert response.json()[0]["is_liked"] is False


# 댓글 작성 시 토큰 3개가 차감되고 거래내역이 기록된다
@pytest.mark.django_db
def test_comment_create_deducts_tokens(
    auth_client: APIClient, post: Post, user: User
) -> None:
    user.token_balance = 5
    user.save(update_fields=["token_balance"])

    response = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글"},
        format="json",
    )

    assert response.status_code == 201
    user.refresh_from_db()
    assert user.token_balance == 2
    tx = TokenTransaction.objects.get(user=user, type="comment_create")
    assert tx.amount == -3
    assert tx.reference_id == response.json()["comment_id"]


# 토큰이 부족하면 402를 반환하고 댓글이 생성되지 않는다
@pytest.mark.django_db
def test_comment_create_insufficient_tokens(
    auth_client: APIClient, post: Post, user: User
) -> None:
    user.token_balance = 2
    user.save(update_fields=["token_balance"])

    response = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글"},
        format="json",
    )

    assert response.status_code == 402
    assert Comment.objects.filter(post=post).count() == 0
    user.refresh_from_db()
    assert user.token_balance == 2


# 하루 5개를 초과하면 429를 반환한다
@pytest.mark.django_db
def test_comment_create_daily_limit(
    auth_client: APIClient, post: Post, user: User
) -> None:
    user.token_balance = 100
    user.save(update_fields=["token_balance"])

    for _ in range(5):
        ok = auth_client.post(
            f"/api/v1/posts/{post.post_id}/comments/",
            {"content": "댓글"},
            format="json",
        )
        assert ok.status_code == 201

    blocked = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "여섯 번째"},
        format="json",
    )

    assert blocked.status_code == 429
    assert Comment.objects.filter(user=user).count() == 5


# 어제 댓글은 오늘 한도에 포함되지 않는다
@pytest.mark.django_db
def test_comment_daily_limit_resets_each_day(
    auth_client: APIClient, post: Post, user: User
) -> None:
    user.token_balance = 100
    user.save(update_fields=["token_balance"])

    # 어제 작성한 댓글 5개를 직접 생성한다.
    yesterday = timezone.now() - timedelta(days=1)
    for _ in range(5):
        c = Comment.objects.create(post=post, user=user, content="어제 댓글")
        Comment.objects.filter(pk=c.pk).update(created_at=yesterday)

    response = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "오늘 첫 댓글"},
        format="json",
    )

    assert response.status_code == 201


# 댓글은 오래된 순(오름차순)으로 반환된다
@pytest.mark.django_db
def test_comments_ordered_ascending(
    auth_client: APIClient, post: Post, user: User
) -> None:
    now = timezone.now()
    contents = ["가장 오래된", "중간", "가장 최근"]
    for i, content in enumerate(contents):
        c = Comment.objects.create(post=post, user=user, content=content)
        Comment.objects.filter(pk=c.pk).update(created_at=now + timedelta(minutes=i))

    response = auth_client.get(f"/api/v1/posts/{post.post_id}/")

    assert response.status_code == 200
    returned = [c["content"] for c in response.json()["comments"]]
    assert returned == contents


# 상세 응답에 오늘 작성한 댓글 수(daily_comment_count)가 포함된다 (#70)
@pytest.mark.django_db
def test_post_detail_includes_daily_comment_count(
    auth_client: APIClient, post: Post, user: User
) -> None:
    # 오늘 2개, 어제 1개 작성 → 오늘 카운트는 2여야 한다.
    Comment.objects.create(post=post, user=user, content="오늘1")
    Comment.objects.create(post=post, user=user, content="오늘2")
    yesterday = Comment.objects.create(post=post, user=user, content="어제")
    Comment.objects.filter(pk=yesterday.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )

    response = auth_client.get(f"/api/v1/posts/{post.post_id}/")

    assert response.status_code == 200
    assert response.json()["daily_comment_count"] == 2
