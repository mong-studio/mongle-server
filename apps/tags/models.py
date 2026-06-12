from django.conf import settings
from django.db import models


class Tag(models.Model):
    tag_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    content = models.CharField(max_length=20)
    color = models.CharField(max_length=7)

    class Meta:
        db_table = "tags"
        constraints = [
            models.UniqueConstraint(fields=["user", "content"], name="unique_user_tag"),
        ]
