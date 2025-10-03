from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from tasks.models import Task
from .serializers import SubordinateSerializer

def get_user_subordinates(user):
    """
    İstifadəçinin roluna görə ona tabe olan işçilərin siyahısını qaytarır.
    Bu məntiq əvvəl KPI app-ında idi, indi mərkəzləşdiririk.
    """
    if user.role in ['admin', 'top_management']:
        return User.objects.filter(is_active=True).exclude(pk=user.pk)
    
    if user.role == 'department_lead':
        if hasattr(user, 'led_department'):
            return User.objects.filter(
                department=user.led_department,
                role__in=['manager', 'employee'],
                is_active=True
            )
    
    if user.role == 'manager':
        if hasattr(user, 'managed_department'):
            return User.objects.filter(
                department=user.managed_department,
                role='employee',
                is_active=True
            )
            
    return User.objects.none()


class SubordinateListView(APIView):
    """Giriş edən rəhbərin tabeliyində olan işçilərin siyahısını qaytarır."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        subordinates = get_user_subordinates(user)

        search_query = request.query_params.get('search', None)
        if search_query:
            subordinates = subordinates.filter(
                Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query)
            )
        
        department_id = request.query_params.get('department', None)
        if department_id:
            subordinates = subordinates.filter(department__id=department_id)

        serializer = SubordinateSerializer(subordinates, many=True)
        return Response(serializer.data)
    
    
class PerformanceSummaryView(APIView):
    """Calculates and returns detailed task performance for a selected user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug=None, *args, **kwargs):
        # If slug is not provided, use the logged-in user
        if not slug:
            target_user = request.user
        else:
            try:
                target_user = User.objects.get(slug=slug)
            except User.DoesNotExist:
                return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Basic task sets
        all_tasks = Task.objects.filter(assignee=target_user)
        done_tasks = all_tasks.filter(status='DONE')
        active_tasks = all_tasks.filter(status__in=['TODO', 'IN_PROGRESS'])

        # Performance Metrics Calculation
        today = timezone.now().date()
        completed_count = done_tasks.count()
        
        # Overdue are tasks past their due_date that are not DONE or CANCELLED
        overdue_count = all_tasks.filter(
            due_date__lt=today, 
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()

        # On-time completion rate
        on_time_completed_count = done_tasks.filter(completed_at__date__lte=F('due_date')).count()
        total_completed = completed_count
        on_time_rate = (on_time_completed_count / total_completed * 100) if total_completed > 0 else 0

        # Average completion time (in days)
        avg_time_days = done_tasks.annotate(
            completion_duration=Func(F('completed_at') - F('created_at'), function='AGE')
        ).aggregate(
            avg_duration=Avg('completion_duration')
        )['avg_duration']
        
        avg_time_str = f"{avg_time_days.days} gün" if avg_time_days else "N/A"
        
        # Priority breakdown for active tasks
        priority_breakdown = active_tasks.values('priority').annotate(count=Count('id'))
        
        summary_data = {
            "user": SubordinateSerializer(target_user).data,
            "task_performance": {
                "total_tasks": all_tasks.count(),
                "completed_count": completed_count,
                "active_count": active_tasks.count(),
                "overdue_count": overdue_count,
                "on_time_rate": round(on_time_rate, 1),
                "avg_completion_time": avg_time_str,
                "priority_breakdown": list(priority_breakdown)
            },
            "kpi_performance": None
        }
        
        return Response(summary_data)