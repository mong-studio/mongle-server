from django.db.models import ProtectedError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tags.models import Tag
from apps.tags.serializers import TagSerializer


class TagListCreateView(generics.ListCreateAPIView):
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        # 태그는 유저별 소유. 다른 유저의 태그가 새지 않게 본인 것만 노출한다.
        return Tag.objects.filter(user=self.request.user).order_by("tag_id")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TagDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "tag_id"

    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        # Todo.tag / Schedule.tag 는 on_delete=PROTECT.
        # 사용 중인 태그는 삭제 대신 409로 막는다.
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({"error": "TAG_IN_USE"}, status=status.HTTP_409_CONFLICT)
