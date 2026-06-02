"""Account models."""

from __future__ import annotations

from typing import ClassVar
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Mongle user account."""

    class Provider(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        KAKAO = "KAKAO", "Kakao"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    user_name = models.CharField(max_length=8)
    job = models.CharField(max_length=50, blank=True)
    birth = models.DateField(null=True, blank=True)
    is_aiconsent = models.BooleanField(default=False)
    token_balance = models.PositiveIntegerField(default=5)
    provider = models.CharField(
        max_length=10,
        choices=Provider.choices,
        default=Provider.EMAIL,
    )
    is_active = models.BooleanField(default=True)
    # is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["user_name"]

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.email
