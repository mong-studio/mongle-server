import uuid

from django.conf import settings
from django.db import models


class Character(models.Model):
    character_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    character_name = models.CharField(max_length=50)
    origin_img_url = models.CharField(max_length=500, blank=True)
    gen_img_url = models.CharField(max_length=500)
    persona = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "characters"


class ImgGenLog(models.Model):
    img_gen_log_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="img_gen_logs",
    )
    gen_cnt = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "img_gen_logs"
