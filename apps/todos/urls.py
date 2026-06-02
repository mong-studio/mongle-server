from django.urls import path

from apps.todos.views import TodoDetailView, TodoListCreateView

# TODO: 추후 수정 필요
urlpatterns = [
    path("", TodoListCreateView.as_view(), name="todo-list"),
    path("<uuid:todo_id>/", TodoDetailView.as_view(), name="todo-detail"),
]
