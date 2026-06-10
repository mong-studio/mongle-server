"""Posts 앱 테스트 - 게시글 목록/상세, 댓글 생성"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.posts.models import Post


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


# 존재하지 않는 게시글에 댓글 작성 시 404 반환 확인
@pytest.mark.django_db
def test_comment_create_post_not_found(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/posts/00000000-0000-0000-0000-000000000000/comments/",
        {"content": "댓글"},
        format="json",
    )
    assert response.status_code == 404
