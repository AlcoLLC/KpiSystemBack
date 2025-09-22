from rest_framework import serializers
from .models import KPIEvaluation
from accounts.models import User
from accounts.serializers import UserSerializer
from tasks.models import Task
from tasks.serializers import TaskSerializer

class KPIEvaluationSerializer(serializers.ModelSerializer):
    evaluator = UserSerializer(read_only=True)
    evaluator_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        source="evaluator", 
        write_only=True, 
        required=False
    )
    evaluatee = UserSerializer(read_only=True)
    evaluatee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="evaluatee", write_only=True
    )

    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), source="task", write_only=True
    )

    class Meta:
        model = KPIEvaluation
        fields = [
            "id", "task", "task_id",
            "evaluator", "evaluator_id",
            "evaluatee", "evaluatee_id",
            "score", "comment", "created_at",
            "evaluation_type" 
        ]
        read_only_fields = ["created_at", "evaluation_type"]