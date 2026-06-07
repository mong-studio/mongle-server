"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from apps.users import signup_views


@require_GET
def health_check(request: object) -> JsonResponse:
    # 서버가 살아있는지 확인하는 헬스체크 API
    # 배포 환경에서 로드밸런서나 모니터링 도구가 주기적으로 호출
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path(
        "api/v1/",
        include(
            [
                path(
                    "auth/email-verification",
                    signup_views.request_email_verification,
                    name="email-verification",
                ),
                path(
                    "auth/email-verification/confirm",
                    signup_views.confirm_email_verification,
                    name="email-verification-confirm",
                ),
                path("auth/signup", signup_views.signup, name="signup"),
                path("auth/", include("apps.users.urls")),
                path("characters/", include("apps.characters.urls")),
                path("todos/", include("apps.todos.urls")),
                path("quests/", include("apps.quests.urls")),
                path("posts/", include("apps.posts.urls")),
            ]
        ),
    ),
]
