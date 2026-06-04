from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.posts.models import Post
from apps.posts.serializers import CommentSerializer, PostSerializer


class PostListView(generics.ListAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Post.objects.all().order_by("-created_at")  # 모든 피드를 최신순으로


class PostDetailView(generics.RetrieveAPIView):
    serializer_class = PostSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Post.objects.all()
    lookup_field = "post_id"


class CommentCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, post_id):
        post = generics.get_object_or_404(Post, post_id=post_id)

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(post=post, user=request.user)

        from apps.posts.tasks import generate_character_reply

        generate_character_reply.apply_async(
            args=[str(comment.comment_id)],
            countdown=600,  # 10분 후 실행
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)
