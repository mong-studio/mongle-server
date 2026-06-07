from django.urls import path

from apps.quests.views import QuestDetailView, QuestListView

urlpatterns = [
    path("", QuestListView.as_view(), name="quest-list"),
    path("<uuid:quest_id>/", QuestDetailView.as_view(), name="quest-detail"),
]
