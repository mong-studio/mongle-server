from django.urls import path

from apps.characters.views import (
    CharacterDeleteView,
    CharacterDetailView,
    CharacterListView,
    CharacterRegisterView,
    GenerationJobCreateView,
    GenerationJobDetailView,
    QuestListView,
    SourceImageCreateView,
)

urlpatterns = [
    path("source-images/", SourceImageCreateView.as_view(), name="source-image-create"),
    path(
        "generation-jobs/",
        GenerationJobCreateView.as_view(),
        name="generation-job-create",
    ),
    path(
        "generation-jobs/<uuid:job_id>/",
        GenerationJobDetailView.as_view(),
        name="generation-job-detail",
    ),
    path("", CharacterListView.as_view(), name="character-list"),
    path("register/", CharacterRegisterView.as_view(), name="character-register"),
    path(
        "<uuid:character_id>/", CharacterDetailView.as_view(), name="character-detail"
    ),
    path(
        "<uuid:character_id>/delete/",
        CharacterDeleteView.as_view(),
        name="character-delete",
    ),
    path(
        "<uuid:character_id>/quests/",
        QuestListView.as_view(),
        name="character-quest-list",
    ),
]
