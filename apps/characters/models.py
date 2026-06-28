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
    # AI 생성 외형 묘사. 확정 등록(CHAR-004) 시 Character.visual 로 옮긴다.
    appearance = models.CharField(max_length=255, blank=True)
    # 이미지 워커가 반환한 정규화 외형. 사용자가 나중에 캐릭터를 확정할 때 복사한다.
    appearance_payload = models.JSONField(null=True, blank=True)
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
    # 원본 사진의 S3 object_key 를 저장한다(URL 아님). 비공개 객체라 조회 시점에
    # presigned GET URL 로 서명해 내려준다 — 저장한 URL 이 만료되는 문제를 피하고,
    # job/source_image(둘 다 SET_NULL)가 지워져도 origin 을 잃지 않는다.
    origin_img_url = models.TextField(blank=True)
    # 생성 이미지 presigned URL. 서명 쿼리로 500자를 넘을 수 있어 TextField.
    gen_img_url = models.TextField()
    persona = models.TextField()
    visual = models.CharField(max_length=255, blank=True)
    # 피드 생성 시 동일한 캐릭터 외형을 재현하기 위한 정규화 데이터.
    appearance_payload = models.JSONField(null=True, blank=True)
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
