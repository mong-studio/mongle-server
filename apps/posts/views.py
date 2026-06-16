import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.posts.models import Post
from apps.posts.serializers import CommentSerializer, PostSerializer
from apps.posts.tasks import generate_character_reply

logger = logging.getLogger(__name__)


_POST_QUERYSET = Post.objects.select_related("character").prefetch_related(
    "comments__user",
    "comments__replies__character",
)


class PostListView(generics.ListAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)
    queryset = _POST_QUERYSET.order_by("-created_at")


class PostDetailView(generics.RetrieveAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)
    queryset = _POST_QUERYSET
    lookup_field = "post_id"


class CommentCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, post_id):
        post = generics.get_object_or_404(Post, post_id=post_id)

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(post=post, user=request.user)

        comment_id = str(comment.comment_id)

        def _schedule_reply() -> None:
            try:
                generate_character_reply.apply_async(
                    args=[comment_id],
                    countdown=600,  # 10분 후 실행
                )
            except Exception as e:
                logger.warning(
                    "답글 예약 실패 (브로커 장애): comment_id=%s, error=%s",
                    comment_id,
                    e,
                )

        transaction.on_commit(_schedule_reply)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
