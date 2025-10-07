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
from django.db.models import Avg
from datetime import datetime
from kpis.models import KPIEvaluation
from accounts.models import User, Department


def get_user_subordinates(user):
    """
    İstifadəçinin roluna görə ona tabe olan işçilərin siyahısını qaytarır.
    """
    queryset = User.objects.none()

    if user.role in ['admin', 'top_management']:
        queryset = User.objects.filter(is_active=True).exclude(pk=user.pk)
    
    elif user.role == 'department_lead':
        try:
            # Departament rəhbərinin rəhbərlik etdiyi departamenti tapır
            led_department = Department.objects.get(lead=user)
            # Həmin departamentdəki menecer və işçiləri tapır
            queryset = User.objects.filter(
                department=led_department,
                role__in=['manager', 'employee'],
                is_active=True
            )
        except Department.DoesNotExist:
            queryset = User.objects.none()
    
    elif user.role == 'manager':
        # DÜZƏLİŞ: Menecerin öz departamentindəki işçiləri görməsini təmin edir
        if user.department:
            queryset = User.objects.filter(
                department=user.department,
                role='employee',
                is_active=True
            )
        else:
            # Menecerin departamenti yoxdursa, heç kimi görməsin
            queryset = User.objects.none()
            
    return queryset.order_by('first_name', 'last_name')


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
         
        if slug == 'me' or slug is None:
            target_user = request.user
        else:
            try:
                target_user = User.objects.get(slug=slug)
            except User.DoesNotExist:
                return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if request.user.role != 'admin' and target_user.role == 'top_management' and request.user != target_user:
             return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        all_tasks = Task.objects.filter(assignee=target_user)
        done_tasks = all_tasks.filter(status='DONE')
        active_tasks = all_tasks.filter(status__in=['TODO', 'IN_PROGRESS'])
        today = timezone.now().date()

         
        completed_count = done_tasks.count()
        overdue_count = all_tasks.filter(
            due_date__lt=today, 
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()
        
         
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
    
class KpiMonthlySummaryView(APIView):
    """
    Seçilmiş istifadəçinin müəyyən bir ay üçün olan tapşırıqlarının
    yekun KPI ballarını və adlarını qaytarır.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug, *args, **kwargs):
        try:
            target_user = User.objects.get(slug=slug)
        except User.DoesNotExist:
            return Response({"detail": "İstifadəçi tapılmadı."}, status=status.HTTP_404_NOT_FOUND)

        try:
            year = int(request.query_params.get('year', datetime.now().year))
            month = int(request.query_params.get('month', datetime.now().month))
        except (ValueError, TypeError):
            return Response({"detail": "İl və ay düzgün formatda deyil."}, status=status.HTTP_400_BAD_REQUEST)

        evaluations = KPIEvaluation.objects.filter(
            evaluatee=target_user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
            task__completed_at__year=year,
            task__completed_at__month=month
        ).select_related('task').order_by('task__completed_at')

        # Dəyişiklik: Artıq daha detallı məlumat qaytarırıq
        evaluations_data = [
            {
                "day": evaluation.task.completed_at.day,
                "score": evaluation.final_score,
                "task_title": evaluation.task.title
            }
            for evaluation in evaluations
        ]

        response_data = {
            'year': year,
            'month': month,
            'evaluations': evaluations_data,
        }

        return Response(response_data)