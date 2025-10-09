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
from accounts.serializers import DepartmentSerializer


class SubordinateListView(APIView):
    """Giriş edən rəhbərin tabeliyində olan işçilərin siyahısını qaytarır."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        subordinates = user.get_subordinates()

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

# performance/views.py

# ... importlar ...

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
        

        all_tasks = Task.objects.filter(assignee=target_user)
        done_tasks = all_tasks.filter(status='DONE')
        today = timezone.now().date()
        
        
        tasks_with_due_date = done_tasks.filter(due_date__isnull=False)
        on_time_completed_count = tasks_with_due_date.filter(completed_at__date__lte=F('due_date')).count()
        
        total_relevant_completed = tasks_with_due_date.count()

        current_overdue_count = all_tasks.filter(
            due_date__lt=today,
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()
        
        total_performance_base = total_relevant_completed + current_overdue_count

        if total_performance_base > 0:
            on_time_rate = (on_time_completed_count / total_performance_base) * 100
        else:
            on_time_rate = 0 
        
        summary_data = {
            "user": SubordinateSerializer(target_user, context={'request': request}).data,
            "task_performance": {
                "total_tasks": all_tasks.count(),
                "completed_count": done_tasks.count(),
                "active_count": all_tasks.filter(status__in=['TODO', 'IN_PROGRESS']).count(),
                "overdue_count": current_overdue_count, 
                "on_time_rate": round(on_time_rate, 1),
                "priority_completion": list(done_tasks.values('priority').annotate(count=Count('id')).order_by('priority')),
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
    

