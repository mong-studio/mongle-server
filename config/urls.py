"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET


@require_GET
def health_check(request: object) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
]
