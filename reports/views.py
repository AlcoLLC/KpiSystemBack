from rest_framework import viewsets, permissions, generics
from django.db.models import Q
from .models import ActivityLog
from .serializers import ActivityLogSerializer, UserFilterSerializer 
from tasks.models import Task
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.views import APIView
from accounts.models import User
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ActivityLogFilter
from .pagination import StandardResultsSetPagination 

class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination 

    filter_backends = [DjangoFilterBackend]
    filterset_class = ActivityLogFilter

    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            return ActivityLog.objects.all().select_related('actor', 'target_user', 'target_task')

        subordinate_ids = user.get_subordinates().values_list('id', flat=True)
        
        visible_user_ids = list(subordinate_ids) + [user.id]

        query = Q(actor_id__in=visible_user_ids) | Q(target_user_id__in=visible_user_ids)
        
        return ActivityLog.objects.filter(query).distinct().select_related('actor', 'target_user', 'target_task')
    
class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        completed_tasks_count = Task.objects.filter(
            status='DONE', 
            completed_at__gte=start_of_month
        ).count()

        in_progress_tasks_count = Task.objects.filter(status='IN_PROGRESS').count()

        if user.role == 'admin':
            active_users_count = User.objects.filter(is_active=True).count()
        else:
            subordinate_ids = user.get_subordinates().values_list('id', flat=True)
            visible_user_ids = list(subordinate_ids) + [user.id]
            active_users_count = User.objects.filter(id__in=visible_user_ids, is_active=True).count()


        stats = {
            'completed': completed_tasks_count,
            'inProgress': in_progress_tasks_count,
            'users': active_users_count,
        }
        return Response(stats)


class UserListView(generics.ListAPIView):
    serializer_class = UserFilterSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None 
    
    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            return User.objects.filter(is_active=True).order_by('first_name')
        
        subordinate_ids = user.get_subordinates().values_list('id', flat=True)
        visible_user_ids = list(subordinate_ids) + [user.id]

        return User.objects.filter(id__in=visible_user_ids, is_active=True).order_by('first_name')