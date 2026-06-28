import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.posts.models import Comment, Post
from apps.posts.serializers import CommentSerializer, PostSerializer
from apps.posts.tasks import generate_character_reply
from apps.users.api_errors import error_response
from apps.users.models import TokenTransaction, User

logger = logging.getLogger(__name__)

# 댓글 작성 정책: 하루 5개까지, 1개당 토큰 3개 소모.
DAILY_COMMENT_LIMIT = 5
COMMENT_TOKEN_COST = 3


def _today_start():
    """오늘 0시(서버 로컬타임)의 aware datetime."""
    return timezone.make_aware(
        timezone.datetime.combine(timezone.localdate(), timezone.datetime.min.time())
    )


def _daily_comment_count(user) -> int:
    return Comment.objects.filter(user=user, created_at__gte=_today_start()).count()


_POST_QUERYSET = Post.objects.select_related("character").prefetch_related(
    "comments__user",
    "comments__replies__character",
)


class PostListView(generics.ListAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return _POST_QUERYSET.filter(character__user=self.request.user).order_by(
            "-created_at"
        )


class PostDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "post_id"

    def get_queryset(self):
        # 본인 캐릭터의 게시물만 조회·삭제할 수 있다(DELETE 시 댓글·답글은 CASCADE).
        return _POST_QUERYSET.filter(character__user=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["daily_comment_count"] = _daily_comment_count(self.request.user)
        return context


class CommentCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, post_id):
        # 서비스 내 피드는 완전 개인용 — 본인 캐릭터 게시물에만 댓글을 달 수 있다.
        post = generics.get_object_or_404(
            Post, post_id=post_id, character__user=request.user
        )

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # 동시성 방지
            user = User.objects.select_for_update().get(pk=request.user.pk)

            if _daily_comment_count(user) >= DAILY_COMMENT_LIMIT:
                return error_response(429, "DAILY_COMMENT_LIMIT_EXCEEDED")

            if user.token_balance < COMMENT_TOKEN_COST:
                return error_response(402, "INSUFFICIENT_TOKEN_BALANCE")

            comment = serializer.save(post=post, user=user)

            user.token_balance -= COMMENT_TOKEN_COST
            user.save(update_fields=["token_balance", "updated_at"])
            TokenTransaction.objects.create(
                user=user,
                amount=-COMMENT_TOKEN_COST,
                type="comment_create",
                reference_id=str(comment.comment_id),
            )

            # 커밋이 확정된 뒤에만 답글 생성을 예약한다(롤백 시 예약 안 함).
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


class PostLikeView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, post_id):
        # 완전 개인용 피드 — 본인 캐릭터 게시물만 좋아요를 토글할 수 있다.
        post = generics.get_object_or_404(
            Post, post_id=post_id, character__user=request.user
        )
        post.is_liked = not post.is_liked
        post.save(update_fields=["is_liked", "updated_at"])
        return Response({"is_liked": post.is_liked}, status=status.HTTP_200_OK)
