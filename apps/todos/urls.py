from django.urls import path

from apps.todos.views import (
    TodoChatAIView,
    TodoCommitAIView,
    TodoCompleteView,
    TodoDetailView,
    TodoGenerateAIView,
    TodoListCreateView,
)

urlpatterns = [
    path("generate/", TodoGenerateAIView.as_view(), name="todo-generate"),
    path("chat/", TodoChatAIView.as_view(), name="todo-chat"),
    path("commit/", TodoCommitAIView.as_view(), name="todo-commit"),
    path("", TodoListCreateView.as_view(), name="todo-list"),
    path("<uuid:todo_id>/", TodoDetailView.as_view(), name="todo-detail"),
    path("<uuid:todo_id>/complete/", TodoCompleteView.as_view(), name="todo-complete"),
]
