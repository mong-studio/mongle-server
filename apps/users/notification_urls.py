from django.urls import path

from apps.users.notification_views import NotificationListView, NotificationReadView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path(
        "<int:notification_id>/read/",
        NotificationReadView.as_view(),
        name="notification-read",
    ),
]
