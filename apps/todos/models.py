import uuid

from django.conf import settings
from django.db import models


class Tag(models.Model):
    tag_id = models.IntegerField(primary_key=True)
    content = models.CharField(max_length=20)
    color = models.CharField(max_length=7)

    class Meta:
        db_table = "tags"


class Todo(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    todo_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todos",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.PROTECT,
        related_name="todos",
    )
    content = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    todo_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "todos"
