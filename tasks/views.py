from rest_framework import viewsets, permissions
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data.get("assignee", creator)

        approved = True if creator == assignee else False
        serializer.save(created_by=creator, approved=approved)
