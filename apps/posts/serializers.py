from rest_framework import serializers

from apps.posts.models import Comment, Post, Reply


class ReplySerializer(serializers.ModelSerializer):
    character_name = serializers.CharField(
        source="character.character_name", read_only=True
    )

    class Meta:
        model = Reply
        fields = ("reply_id", "character", "character_name", "content", "created_at")
        read_only_fields = fields


class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.user_name", read_only=True)
    replies = ReplySerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = (
            "comment_id",
            "user",
            "user_name",
            "content",
            "created_at",
            "replies",
        )
        read_only_fields = (
            "comment_id",
            "user",
            "user_name",
            "created_at",
            "replies",
        )


class PostSerializer(serializers.ModelSerializer):
    character_name = serializers.CharField(
        source="character.character_name", read_only=True
    )
    comments = CommentSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = (
            "post_id",
            "character",
            "character_name",
            "img_url",
            "content",
            "is_liked",
            "comments",
            "created_at",
        )
        read_only_fields = ("post_id", "created_at")
