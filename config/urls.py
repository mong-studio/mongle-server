"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET


@require_GET
def health_check(request: object) -> JsonResponse:
    # 서버가 살아있는지 확인하는 헬스체크 API
    # 배포 환경에서 로드밸런서나 모니터링 도구가 주기적으로 호출
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("api/auth/", include("apps.users.urls")),
    path("api/characters/", include("apps.characters.urls")),
    path("api/todos/", include("apps.todos.urls")),
    path("api/quests/", include("apps.quests.urls")),
    path("api/posts/", include("apps.posts.urls")),
]
