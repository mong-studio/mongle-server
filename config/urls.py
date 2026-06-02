"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET

from apps.accounts import views as account_views


@require_GET
def health_check(request: object) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path(
        "auth/email-verification",
        account_views.request_email_verification,
        name="email-verification",
    ),
    path(
        "auth/email-verification/confirm",
        account_views.confirm_email_verification,
        name="email-verification-confirm",
    ),
    path("auth/signup", account_views.signup, name="signup"),
]
