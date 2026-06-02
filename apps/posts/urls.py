from django.urls import path

from apps.posts.views import CommentCreateView, PostDetailView, PostListView

# GET  /api/posts/                          → 전체 피드 목록
# GET  /api/posts/{post_id}/                → 특정 피드 상세 (댓글 포함)
# POST /api/posts/{post_id}/comments/       → 댓글 작성
urlpatterns = [
    path("", PostListView.as_view(), name="post-list"),
    path("<uuid:post_id>/", PostDetailView.as_view(), name="post-detail"),
    path(
        "<uuid:post_id>/comments/", CommentCreateView.as_view(), name="comment-create"
    ),
]
