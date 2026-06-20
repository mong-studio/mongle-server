from django.urls import path

from apps.todos.views import (
    CalendarMonthView,
    ScheduleCreateView,
    ScheduleDetailView,
)

urlpatterns = [
    path("schedules/", ScheduleCreateView.as_view(), name="schedule-create"),
    path(
        "schedules/<uuid:schedule_id>/",
        ScheduleDetailView.as_view(),
        name="schedule-detail",
    ),
    path("calendar/", CalendarMonthView.as_view(), name="calendar"),
]
