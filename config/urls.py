"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

# include: 다른 파일의 URL 목록을 가져오는 함수 — 앱마다 urls.py를 따로 관리하고 여기서 모음
from django.views.decorators.http import require_GET


@require_GET  # GET 요청만 허용 (POST 등은 405 Method Not Allowed 반환)
def health_check(request: object) -> JsonResponse:
    # 서버가 살아있는지 확인하는 헬스체크 API
    # 배포 환경에서 로드밸런서나 모니터링 도구가 주기적으로 호출
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/characters/", include("apps.characters.urls")),
    path("api/todos/", include("apps.todos.urls")),
    path("api/quests/", include("apps.quests.urls")),
    path("api/posts/", include("apps.posts.urls")),
]
