from rest_framework import serializers
from .models import Task
from accounts.models import User
from kpis.serializers import KPIEvaluationSerializer
from accounts.serializers import UserSerializer

class TaskSerializer(serializers.ModelSerializer):
    assignee_details = serializers.StringRelatedField(source='assignee', read_only=True)
    created_by_details = serializers.StringRelatedField(source='created_by', read_only=True)
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all()) 
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    evaluations = KPIEvaluationSerializer(many=True, read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)

    assignee_obj = serializers.SerializerMethodField(read_only=True)
    created_by_obj = serializers.SerializerMethodField(read_only=True)

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
            'position_name',
            'created_by',
            'created_by_details',
            'start_date',
            'due_date',
            'approved',
            'created_at',
            'status_display',
            'priority_display',
            'evaluations',
            'assignee_obj',
            'created_by_obj', 
        ]
        read_only_fields = [
            'created_by',
            'created_by_details',
            'approved',
            'created_at',
        ]

    def get_assignee_obj(self, obj):
        if obj.assignee:
            return UserSerializer(obj.assignee, context=self.context).data
        return None

    def get_created_by_obj(self, obj):
        if obj.created_by:
            return UserSerializer(obj.created_by, context=self.context).data
        return None

class TaskAssigneeSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'position_name', 'profile_photo']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        photo_url = representation.get('profile_photo')
        if request and photo_url:
            representation['profile_photo'] = request.build_absolute_uri(photo_url)
        return representation

class TaskUserSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'position_name', 'role']
