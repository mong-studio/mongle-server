from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.tags.models import Tag
from apps.tags.serializers import TagSerializer


class TagListView(generics.ListAPIView):
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Tag.objects.order_by("tag_id")


class TagDetailView(generics.RetrieveAPIView):
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Tag.objects.all()
    lookup_field = "tag_id"
