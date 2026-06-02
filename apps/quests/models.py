import uuid

from django.db import models

from apps.characters.models import Character
from apps.todos.models import Todo


class Quest(models.Model):
    quest_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="quests",
    )
    todo = models.ForeignKey(
        Todo,
        on_delete=models.CASCADE,
        related_name="quests",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quests"
