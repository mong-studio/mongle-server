from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.todos.models import Todo
from apps.todos.serializers import TodoSerializer


class TodoListCreateView(generics.ListCreateAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        # 내 TODO만 조회, 최신순 정렬
        return Todo.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TodoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TodoSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "todo_id"

    def get_queryset(self):
        # 내 TODO만 수정/삭제 가능
        return Todo.objects.filter(user=self.request.user)
