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
    """Seçilmiş istifadəçinin tapşırıq performansını hesablayır."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug, *args, **kwargs):
        try:
            target_user = User.objects.get(slug=slug)
        except User.DoesNotExist:
            return Response({"detail": "İstifadəçi tapılmadı."}, status=status.HTTP_404_NOT_FOUND)

        all_tasks = Task.objects.filter(assignee=target_user)
        completed_tasks = all_tasks.filter(status='DONE')
        
        today = timezone.now().date()
        overdue_tasks_count = all_tasks.filter(
            due_date__lt=today, 
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()
        
        total_finished_count = completed_tasks.count() + overdue_tasks_count
        completion_rate = 0
        if total_finished_count > 0:
            completion_rate = round((completed_tasks.count() / total_finished_count) * 100, 1)

        summary_data = {
            "user": SubordinateSerializer(target_user).data,
            "task_performance": {
                "completed_count": completed_tasks.count(),
                "overdue_count": overdue_tasks_count,
                "completion_rate": completion_rate,
            },
            "kpi_performance": None
        }
        
        return Response(summary_data)