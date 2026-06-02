from rest_framework import generics  # CRUD를 자동으로 처리해주는 DRF 제네릭 View
from rest_framework.permissions import IsAuthenticated

from apps.characters.models import Character
from apps.characters.serializers import CharacterSerializer


class CharacterListCreateView(generics.ListCreateAPIView):
    serializer_class = CharacterSerializer
    permission_classes = (IsAuthenticated,)  # 로그인한 사람만 접근 가능

    def get_queryset(self):
        # "내 캐릭터 중 활성화된 것만 조회"
        # 다른 유저의 캐릭터는 절대 반환되지 않음
        return Character.objects.filter(user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        # 캐릭터 생성 시 user 필드를 현재 로그인한 유저로 자동 설정
        # 앱에서 user_id를 직접 보내지 않아도 됨 (보안상 서버에서 설정)
        serializer.save(user=self.request.user)


class CharacterDetailView(generics.RetrieveUpdateDestroyAPIView):
    # RetrieveUpdateDestroyAPIView: 조회/수정/삭제를 한 클래스에서 모두 처리

    serializer_class = CharacterSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "character_id"  # URL의 {character_id} 값으로 DB에서 캐릭터를 찾음

    def get_queryset(self):
        # 내 캐릭터만 수정/삭제 가능 (다른 유저의 캐릭터는 404 반환)
        return Character.objects.filter(user=self.request.user)
