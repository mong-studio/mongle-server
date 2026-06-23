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
    # img_url 컬럼엔 생성 시점의 presigned URL(만료 1h)이 들어있다. 그대로 내려주면
    # 1시간 뒤 'Request has expired'(403)로 깨지므로, 조회 시점에 key를 추출해 새로
    # 서명한다. 캐릭터 gen_img_url 과 동일한 패턴.
    img_url = serializers.SerializerMethodField()

    def get_img_url(self, obj: Post) -> str:
        from apps.characters.serializers import _resolve_gen_img_url

        return _resolve_gen_img_url(obj.img_url)

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
