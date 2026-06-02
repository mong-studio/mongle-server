from django.urls import path

from apps.characters.views import CharacterDetailView, CharacterListCreateView

urlpatterns = [
    # TODO: 추후 수정 필요
    path("", CharacterListCreateView.as_view(), name="character-list"),
    path(
        "<uuid:character_id>/", CharacterDetailView.as_view(), name="character-detail"
    ),
]
