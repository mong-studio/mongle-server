from django.urls import path

from apps.posts.views import (
    CommentCreateView,
    PostDetailView,
    PostLikeView,
    PostListView,
)

urlpatterns = [
    path("", PostListView.as_view(), name="post-list"),
    path("<uuid:post_id>/", PostDetailView.as_view(), name="post-detail"),
    path(
        "<uuid:post_id>/comments/", CommentCreateView.as_view(), name="comment-create"
    ),
    path("<uuid:post_id>/like/", PostLikeView.as_view(), name="post-like"),
]
