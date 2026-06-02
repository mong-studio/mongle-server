from django.urls import path

from apps.posts.views import CommentCreateView, PostDetailView, PostListView

# TODO: 추후 수정 필요
urlpatterns = [
    path("", PostListView.as_view(), name="post-list"),
    path("<uuid:post_id>/", PostDetailView.as_view(), name="post-detail"),
    path(
        "<uuid:post_id>/comments/", CommentCreateView.as_view(), name="comment-create"
    ),
]
