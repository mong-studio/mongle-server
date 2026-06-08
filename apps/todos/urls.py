from django.urls import path

from apps.todos.views import TodoDetailView, TodoListCreateView

urlpatterns = [
    path("", TodoListCreateView.as_view(), name="todo-list"),
    path("<uuid:todo_id>/", TodoDetailView.as_view(), name="todo-detail"),
]
