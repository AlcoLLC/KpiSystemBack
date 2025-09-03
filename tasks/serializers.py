from rest_framework import serializers
from .models import Task
from accounts.models import User
from accounts.serializers import UserSerializer


class TaskSerializer(serializers.ModelSerializer):
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="assignee", write_only=True
    )
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "title", "description", "status", "priority",
            "assignee", "assignee_id", "created_by",
            "start_date", "due_date",
            "approved", "created_at"
        ]
        read_only_fields = ["approved", "created_by", "created_at"]
