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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Reports ActivityLog] User: {user.get_full_name()}, factory_role: {user.factory_role}, role: {user.role}")

        if user.role == 'admin':
            return ActivityLog.objects.all().select_related('actor', 'target_user', 'target_task')

        if user.factory_role == "top_management":
            logger.info("[Reports ActivityLog] Factory top management - showing all office logs")
            
            office_user_ids = User.objects.filter(
                factory_role__isnull=True,
                role__isnull=False,
                is_active=True
            ).exclude(
                role__in=['admin', 'ceo']
            ).values_list('id', flat=True)
            
            query = Q(actor_id__in=office_user_ids) | Q(target_user_id__in=office_user_ids)
            
            queryset = ActivityLog.objects.filter(query).distinct().select_related('actor', 'target_user', 'target_task')
            logger.info(f"[Reports ActivityLog] Factory top management logs count: {queryset.count()}")
            return queryset

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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Reports DashboardStats] User: {user.get_full_name()}, factory_role: {user.factory_role}, role: {user.role}")
        
        if user.factory_role == "top_management":
            logger.info("[Reports DashboardStats] Factory top management - showing office stats")
            
            office_user_ids = User.objects.filter(
                factory_role__isnull=True,
                role__isnull=False,
                is_active=True
            ).exclude(
                role__in=['admin', 'ceo']
            ).values_list('id', flat=True)
            
            completed_tasks_count = Task.objects.filter(
                assignee_id__in=office_user_ids,
                status='DONE', 
                completed_at__gte=start_of_month
            ).count()

            in_progress_tasks_count = Task.objects.filter(
                assignee_id__in=office_user_ids,
                status='IN_PROGRESS'
            ).count()

            active_users_count = len(office_user_ids)
            
            logger.info(f"[Reports DashboardStats] Factory TM stats - completed: {completed_tasks_count}, in_progress: {in_progress_tasks_count}, users: {active_users_count}")
        
        elif user.role == 'admin':
            completed_tasks_count = Task.objects.filter(
                status='DONE', 
                completed_at__gte=start_of_month
            ).count()

            in_progress_tasks_count = Task.objects.filter(status='IN_PROGRESS').count()
            active_users_count = User.objects.filter(is_active=True).count()
        
        else:
            subordinate_ids = user.get_subordinates().values_list('id', flat=True)
            visible_user_ids = list(subordinate_ids) + [user.id]
            
            completed_tasks_count = Task.objects.filter(
                assignee_id__in=visible_user_ids,
                status='DONE', 
                completed_at__gte=start_of_month
            ).count()

            in_progress_tasks_count = Task.objects.filter(
                assignee_id__in=visible_user_ids,
                status='IN_PROGRESS'
            ).count()
            
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
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Reports UserList] User: {user.get_full_name()}, factory_role: {user.factory_role}, role: {user.role}")

        if user.role == 'admin':
            return User.objects.filter(is_active=True).order_by('first_name')
        
        if user.factory_role == "top_management":
            logger.info("[Reports UserList] Factory top management - showing all office users")
            queryset = User.objects.filter(
                factory_role__isnull=True,
                role__isnull=False,
                is_active=True
            ).exclude(
                role__in=['admin', 'ceo']
            ).order_by('first_name')
            logger.info(f"[Reports UserList] Factory TM users count: {queryset.count()}")
            return queryset
        
        subordinate_ids = user.get_subordinates().values_list('id', flat=True)
        visible_user_ids = list(subordinate_ids) + [user.id]

        return User.objects.filter(id__in=visible_user_ids, is_active=True).order_by('first_name')