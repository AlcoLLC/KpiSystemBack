from rest_framework import serializers
from .models import Task
from accounts.models import User
from accounts.serializers import UserSerializer
from kpis.serializers import KPIEvaluationSerializer


class TaskAssigneeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'profile_photo']

    def to_representation(self, instance):
        represenation = super().to_representation(instance)
        request = self.context.get('request')
        if instance.profile_photo and hasattr(instance.profile_photo, 'url'):
            represenation['profile_photo'] = request.build_absolute_uri(instance.profile_photo.url)
        return represenation


class TaskSerializer(serializers.ModelSerializer):
    assignee = TaskAssigneeSerializer(read_only=True)
    created_by = TaskAssigneeSerializer(read_only=True)
    
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='assignee', write_only=True
    )

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'status', 'priority', 
            'assignee', 'assignee_id', 'created_by', 'start_date', 'due_date', 
            'approved', 'created_at', 'status_display', 'priority_display'
        ]
        read_only_fields = ['created_by', 'approved', 'created_at']

class TaskUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'role', 'department']

    def get_full_name(self, obj):
        return obj.get_full_name()
