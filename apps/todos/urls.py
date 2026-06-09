from django.urls import path

from apps.todos.views import (
    TagDetailView,
    TagListCreateView,
    TodoChatAIView,
    TodoCommitAIView,
    TodoDetailView,
    TodoGenerateAIView,
    TodoListCreateView,
)

urlpatterns = [
    path("generate/", TodoGenerateAIView.as_view(), name="todo-generate"),
    path("chat/", TodoChatAIView.as_view(), name="todo-chat"),
    path("commit/", TodoCommitAIView.as_view(), name="todo-commit"),
    path("tags/", TagListCreateView.as_view(), name="tag-list"),
    path("tags/<int:tag_id>/", TagDetailView.as_view(), name="tag-detail"),
    path("", TodoListCreateView.as_view(), name="todo-list"),
    path("<uuid:todo_id>/", TodoDetailView.as_view(), name="todo-detail"),
]
