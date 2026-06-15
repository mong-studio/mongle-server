from typing import cast

from django.db.models import QuerySet
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import Notification, User
from apps.users.notification_serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView[Notification]):
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet[Notification]:
        user = cast(User, self.request.user)
        return Notification.objects.filter(user=user).order_by("-created_at")


class NotificationReadView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request: Request, notification_id: int) -> Response:
        user = cast(User, request.user)
        notification = generics.get_object_or_404(
            Notification,
            notification_id=notification_id,
            user=user,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read", "updated_at"])
        return Response(NotificationSerializer(notification).data)
