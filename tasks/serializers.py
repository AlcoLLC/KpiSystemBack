from rest_framework import serializers
from .models import Task
from accounts.models import User
from accounts.serializers import UserSerializer
from kpis.serializers import KPIEvaluationSerializer


class TaskSerializer(serializers.ModelSerializer):
    assignee_details = serializers.StringRelatedField(source='assignee', read_only=True)
    created_by_details = serializers.StringRelatedField(source='created_by', read_only=True)

    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    evaluations = KPIEvaluationSerializer(many=True, read_only=True)

    class Meta:
        model = Task

        fields = [
            'id',
            'title',
            'description',
            'status',
            'priority',
            'assignee',
            'assignee_details',
            'created_by',
            'created_by_details', 
            'start_date',
            'due_date',
            'approved',
            'created_at',
            'status_display',
            'priority_display',
            'evaluations',
        ]

        read_only_fields = [
            'created_by',
            'created_by_details',
            'approved',
            'created_at',
        ]

        def get_assignee_details(self, obj):
            if obj.assignee:
                full_name = obj.assignee.get_full_name()
                return full_name if full_name else obj.assignee.username
            return None

    def get_created_by_details(self, obj):
        if obj.created_by:
            full_name = obj.created_by.get_full_name()
            return full_name if full_name else obj.created_by.username
        return None

class TaskUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'role', 'department']

    def get_full_name(self, obj):
        return obj.get_full_name()