"""Posts 앱 테스트 - 게시글 목록/상세, 댓글 생성"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.posts.models import Post


@pytest.mark.django_db
def test_post_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/posts/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_post_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_post_list_returns_posts(auth_client: APIClient, post: Post) -> None:
    # PostSerializer 필드명(img_url, content)이 모델과 일치하는지 검증
    # 이전에 image_url/caption 으로 잘못 선언되어 500이 났던 회귀 방지용 테스트
    response = auth_client.get("/api/v1/posts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["content"] == "테스트 게시글"
    assert data[0]["img_url"] == "https://example.com/img.png"
    assert "comments" in data[0]


@pytest.mark.django_db
def test_post_detail_unauthenticated(post: Post) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/posts/{post.post_id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_post_detail_authenticated(auth_client: APIClient, post: Post) -> None:
    response = auth_client.get(f"/api/v1/posts/{post.post_id}/")
    assert response.status_code == 200
    assert response.json()["content"] == "테스트 게시글"


@pytest.mark.django_db
def test_post_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/posts/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_comment_create_unauthenticated(post: Post) -> None:
    client = APIClient()
    response = client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글 내용"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_comment_create_success(auth_client: APIClient, post: Post) -> None:
    response = auth_client.post(
        f"/api/v1/posts/{post.post_id}/comments/",
        {"content": "댓글 내용"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["content"] == "댓글 내용"


@pytest.mark.django_db
def test_comment_create_post_not_found(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/posts/00000000-0000-0000-0000-000000000000/comments/",
        {"content": "댓글"},
        format="json",
    )
    assert response.status_code == 404
