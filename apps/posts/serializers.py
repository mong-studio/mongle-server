from rest_framework import serializers

from apps.posts.models import Comment, Post


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ("comment_id", "user", "content", "created_at")
        read_only_fields = ("comment_id", "user", "created_at")


class PostSerializer(serializers.ModelSerializer):
    comments = CommentSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = (
            "post_id",
            "character",
            "image_url",
            "caption",
            "comments",
            "created_at",
        )
        read_only_fields = ("post_id", "created_at")
