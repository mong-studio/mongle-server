from django.urls import path

from apps.todos.views import (
    TodoChatAIJobView,
    TodoChatAIView,
    TodoCompleteView,
    TodoConfirmView,
    TodoDetailView,
    TodoExtendView,
    TodoFailView,
    TodoGenerateAIView,
    TodoListCreateView,
    TodoPlannerConfirmView,
    TodoQuestPreviewView,
    TodoQuestSyncView,
)

urlpatterns = [
    path("generate/", TodoGenerateAIView.as_view(), name="todo-generate"),
    path("chat/", TodoChatAIView.as_view(), name="todo-chat"),
    path("chat/<str:job_id>/", TodoChatAIJobView.as_view(), name="todo-chat-job"),
    path(
        "planner-confirm/",
        TodoPlannerConfirmView.as_view(),
        name="todo-planner-confirm",
    ),
    path("quest-preview/", TodoQuestPreviewView.as_view(), name="todo-quest-preview"),
    path("sync-quests/", TodoQuestSyncView.as_view(), name="todo-sync-quests"),
    path("confirm/", TodoConfirmView.as_view(), name="todo-confirm"),
    path("", TodoListCreateView.as_view(), name="todo-list"),
    path("<uuid:todo_id>/", TodoDetailView.as_view(), name="todo-detail"),
    path("<uuid:todo_id>/complete/", TodoCompleteView.as_view(), name="todo-complete"),
    path("<uuid:todo_id>/fail/", TodoFailView.as_view(), name="todo-fail"),
    path("<uuid:todo_id>/extend/", TodoExtendView.as_view(), name="todo-extend"),
]
