"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from apps.accounts import views as account_views


@require_GET
def health_check(request: object) -> JsonResponse:
    # 서버가 살아있는지 확인하는 헬스체크 API
    # 배포 환경에서 로드밸런서나 모니터링 도구가 주기적으로 호출
    return JsonResponse({"status": "ok"})


# TODO: 추후 수정 필요
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
    path("api/auth/", include("apps.users.urls")),
    path("api/characters/", include("apps.characters.urls")),
    path("api/todos/", include("apps.todos.urls")),
    path("api/quests/", include("apps.quests.urls")),
    path("api/posts/", include("apps.posts.urls")),
]
