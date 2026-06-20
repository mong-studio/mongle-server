from django.urls import path

from apps.todos.views import (
    TodoChatAIView,
    TodoCompleteView,
    TodoConfirmView,
    TodoDetailView,
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
]
