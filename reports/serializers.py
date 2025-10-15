from rest_framework import serializers
from .models import ActivityLog
from accounts.serializers import UserSerializer
from accounts.models import User

class ActivityLogSerializer(serializers.ModelSerializer):
    actor_details = UserSerializer(source='actor', read_only=True)
    description = serializers.SerializerMethodField()
    action_icon = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = [
            'id', 
            'actor_details', 
            'action_type', 
            'description', 
            'action_icon',
            'timestamp',
            'details'
        ]

    def get_action_icon(self, obj):
        icon_map = {
            'TASK_CREATED': 'add',
            'TASK_STATUS_CHANGED': 'change_status',
            'TASK_APPROVED': 'approve',
            'KPI_TASK_EVALUATED': 'star',
            'KPI_USER_EVALUATED': 'star_monthly'
        }
        return icon_map.get(obj.action_type, 'default')

    def get_description(self, obj):
        actor_name = obj.actor.get_full_name() or obj.actor.username
        details = obj.details

        if obj.action_type == 'TASK_CREATED':
            task_title = details.get('task_title', 'N/A')
            return f"'{task_title}' adlı yeni tapşırıq yaratdı."

        elif obj.action_type == 'TASK_STATUS_CHANGED':
            task_title = details.get('task_title', 'N/A')
            old_status = details.get('old_status', 'N/A')
            new_status = details.get('new_status', 'N/A')
            return f"'{task_title}' tapşırığının statusunu '{old_status}'-dan '{new_status}'-a dəyişdi."

        elif obj.action_type == 'TASK_APPROVED':
            task_title = details.get('task_title', 'N/A')
            return f"'{task_title}' tapşırığını təsdiq etdi."

        elif obj.action_type == 'KPI_TASK_EVALUATED':
            task_title = details.get('task_title', 'N/A')
            score = details.get('score', 'N/A')
            return f"'{task_title}' tapşırığını {score}/10 ulduz ilə qiymətləndirdi."

        elif obj.action_type == 'KPI_USER_EVALUATED':
            month = details.get('month', 'N/A')
            score = details.get('score', 'N/A')
            target_user_name = obj.target_user.get_full_name() if obj.target_user else 'bir işçini'
            return f"{target_user_name} adlı işçinin {month} ayı üzrə fəaliyyətini {score}/10 bal ilə qiymətləndirdi."
            
        return "Naməlum fəaliyyət."

class UserFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name']