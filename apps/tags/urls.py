from django.urls import path

from apps.tags.views import TagDetailView, TagListView

urlpatterns = [
    path("", TagListView.as_view(), name="tag-list"),
    path("<int:tag_id>/", TagDetailView.as_view(), name="tag-detail"),
]
