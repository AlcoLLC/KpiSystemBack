from rest_framework import serializers
from .models import Task
from accounts.models import User
from kpis.serializers import KPIEvaluationSerializer
from accounts.serializers import UserSerializer

class TaskSerializer(serializers.ModelSerializer):
    assignee_details = serializers.StringRelatedField(source='assignee', read_only=True)
    created_by_details = serializers.StringRelatedField(source='created_by', read_only=True)
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all()) # Bu, yazmaq üçün qalır
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    evaluations = KPIEvaluationSerializer(many=True, read_only=True)

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

    # --- YENİ ƏLAVƏ EDİLƏN METODLAR ---
    def get_assignee_obj(self, obj):
        if obj.assignee:
            return UserSerializer(obj.assignee, context=self.context).data
        return None

    def get_created_by_obj(self, obj):
        if obj.created_by:
            return UserSerializer(obj.created_by, context=self.context).data
        return None

# Digər serializer-lərə toxunmuruq
class TaskAssigneeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'profile_photo']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        photo_url = representation.get('profile_photo')
        if request and photo_url:
            representation['profile_photo'] = request.build_absolute_uri(photo_url)
        return representation

class TaskUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'role', 'department']

    def get_full_name(self, obj):
        return obj.get_full_name()