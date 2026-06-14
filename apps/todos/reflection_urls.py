from django.urls import path

from apps.todos.reflection_views import (
    ReflectionContextView,
    ReflectionCreateView,
    ReflectionDateView,
    ReflectionDetailView,
)

urlpatterns = [
    path("context/<str:date_text>/", ReflectionContextView.as_view(), name="context"),
    path("", ReflectionCreateView.as_view(), name="create"),
    path("<uuid:reflection_id>/", ReflectionDetailView.as_view(), name="detail"),
    path("<str:date_text>/", ReflectionDateView.as_view(), name="date-detail"),
]
