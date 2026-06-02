from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.quests.models import Quest
from apps.quests.serializers import QuestSerializer


class QuestListView(generics.ListAPIView):
    serializer_class = QuestSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        # "내 캐릭터에게 배정된 퀘스트만 조회"
        return Quest.objects.filter(character__user=self.request.user).order_by(
            "-created_at"
        )


class QuestDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = QuestSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "quest_id"

    def get_queryset(self):
        return Quest.objects.filter(character__user=self.request.user)
