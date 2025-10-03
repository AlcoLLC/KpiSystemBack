from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Count, Q, F, Avg, Func
from django.utils import timezone
from django.db.models import Avg, F, Func, Case, When, IntegerField
from datetime import timedelta
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

        serializer = SubordinateSerializer(subordinates, many=True, context={'request': request})
        return Response(serializer.data)

class PerformanceSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug=None, *args, **kwargs):
        # DÜZƏLİŞ: slug olmasa, sorğunu göndərən istifadəçini götürür
        if slug == 'me' or slug is None:
            target_user = request.user
        else:
            try:
                target_user = User.objects.get(slug=slug)
            except User.DoesNotExist:
                return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # İcazə yoxlaması: İstifadəçi özündən yuxarıdakının performansına baxa bilməz (admin xaric)
        if request.user.role != 'admin' and target_user.role == 'top_management' and request.user != target_user:
             return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        all_tasks = Task.objects.filter(assignee=target_user)
        done_tasks = all_tasks.filter(status='DONE')
        active_tasks = all_tasks.filter(status__in=['TODO', 'IN_PROGRESS'])
        today = timezone.now().date()

        # Performans göstəricilərinin hesablanması (daha detallı)
        completed_count = done_tasks.count()
        overdue_count = all_tasks.filter(
            due_date__lt=today, 
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()
        
        # Vaxtında tamamlama faizi (yalnız bitmə tarixi olanlar üçün)
        tasks_with_due_date = done_tasks.filter(due_date__isnull=False)
        on_time_completed_count = tasks_with_due_date.filter(completed_at__date__lte=F('due_date')).count()
        total_relevant_completed = tasks_with_due_date.count()
        on_time_rate = (on_time_completed_count / total_relevant_completed * 100) if total_relevant_completed > 0 else 100

        # Prioritetə görə tamamlanmış tapşırıqlar
        priority_completion = done_tasks.values('priority').annotate(count=Count('id')).order_by('priority')

        summary_data = {
            "user": SubordinateSerializer(target_user, context={'request': request}).data,
            "task_performance": {
                "total_tasks": all_tasks.count(),
                "completed_count": completed_count,
                "active_count": active_tasks.count(),
                "overdue_count": overdue_count,
                "on_time_rate": round(on_time_rate, 1),
                "priority_completion": list(priority_completion),
            },
        }
        
        return Response(summary_data)