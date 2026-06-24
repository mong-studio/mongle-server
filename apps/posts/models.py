import uuid

from django.conf import settings
from django.db import models

from apps.characters.models import Character
from apps.quests.models import Quest


class Post(models.Model):
    post_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    content = models.CharField(max_length=150)
    img_url = models.CharField(max_length=500)
    is_liked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posts"


class Comment(models.Model):
    comment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    content = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comments"
        ordering = ("created_at",)


class Reply(models.Model):
    reply_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "replies"
        ordering = ("created_at",)
