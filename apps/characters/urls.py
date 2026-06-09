from django.urls import path

from apps.characters.views import (
    CharacterDetailView,
    CharacterGenerateAIView,
    CharacterListCreateView,
)

urlpatterns = [
    path("generate/", CharacterGenerateAIView.as_view(), name="character-generate"),
    path("", CharacterListCreateView.as_view(), name="character-list"),
    path(
        "<uuid:character_id>/", CharacterDetailView.as_view(), name="character-detail"
    ),
]
