from rest_framework import serializers
from .models import Task
from accounts.models import User
from accounts.serializers import UserSerializer

class TaskSerializer(serializers.ModelSerializer):
    assignee_details = serializers.SerializerMethodField()  # DÜZƏLİŞ
    created_by_details = serializers.SerializerMethodField()  # DÜZƏLİŞ
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

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
        ]
        read_only_fields = [
            'created_by',
            'created_by_details',
            'approved',
            'created_at',
            'status',
        ]

    def get_assignee_details(self, obj):
        if obj.assignee:
            # İstifadəçinin tam adını (first_name + last_name) götürürük
            full_name = obj.assignee.get_full_name()
            # Əgər tam adı yoxdursa, username-ni qaytarırıq
            return full_name if full_name else obj.assignee.username
        return None  # Təyin edilən yoxdursa, boş qaytarırıq

    def get_created_by_details(self, obj):
        """
        'created_by_details' sahəsi üçün məlumat qaytarır.
        """
        if obj.created_by:
            full_name = obj.created_by.get_full_name()
            return full_name if full_name else obj.created_by.username
        return None