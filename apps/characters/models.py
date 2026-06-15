import uuid

from django.conf import settings
from django.db import models


class SourceImage(models.Model):
    class Status(models.TextChoices):
        PENDING_UPLOAD = "PENDING_UPLOAD"
        UPLOAD_COMPLETED = "UPLOAD_COMPLETED"
        UPLOAD_EXPIRED = "UPLOAD_EXPIRED"

    source_img_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="source_images",
    )
    object_key = models.CharField(max_length=500)
    content_type = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING_UPLOAD
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_images"


class CharacterGenerationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED"
        IN_PROGRESS = "IN_PROGRESS"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"
        CONSUMED = "CONSUMED"

    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generation_jobs",
    )
    source_image = models.ForeignKey(
        SourceImage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_jobs",
    )
    personality_keywords = models.JSONField(default=list)
    custom_prompt = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED
    )
    gen_img_object_key = models.CharField(max_length=500, blank=True)
    gen_img_url = models.TextField(blank=True)
    persona = models.TextField(blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "character_generation_jobs"


class Character(models.Model):
    character_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="characters",
    )
    generation_job = models.OneToOneField(
        CharacterGenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character",
    )
    character_name = models.CharField(max_length=8)
    # 이미지 URL은 presigned 서명 쿼리로 500자를 넘을 수 있어 TextField 로 둔다.
    origin_img_url = models.TextField(blank=True)
    gen_img_url = models.TextField()
    persona = models.TextField()
    visual = models.CharField(max_length=255, blank=True)
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
