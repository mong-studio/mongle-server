"""User model managers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from apps.accounts.models import User

EMAIL_REQUIRED_MESSAGE = "The email field must be set."
SUPERUSER_REQUIRED_MESSAGE = "Superuser must have is_superuser=True."


class UserManager(BaseUserManager["User"]):
    """Manager for email-based users."""

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        if not email:
            raise ValueError(EMAIL_REQUIRED_MESSAGE)

        normalized_email = self.normalize_email(email).lower()
        user = self.model(email=normalized_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_superuser") is not True:
            raise ValueError(SUPERUSER_REQUIRED_MESSAGE)

        return self.create_user(email, password, **extra_fields)
