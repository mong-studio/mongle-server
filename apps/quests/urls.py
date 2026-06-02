from django.urls import path

from apps.quests.views import QuestDetailView, QuestListView

# TODO: 추후 수정 필요
urlpatterns = [
    path("", QuestListView.as_view(), name="quest-list"),
    path("<uuid:quest_id>/", QuestDetailView.as_view(), name="quest-detail"),
]
