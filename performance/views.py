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
from accounts.models import User
from django.db.models import Avg
from datetime import timedelta


class SubordinateListView(APIView):
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

        completed_count = done_tasks.count()
        overdue_count = all_tasks.filter(
            due_date__lt=today, 
            status__in=['PENDING', 'TODO', 'IN_PROGRESS']
        ).count()
        
        three_months_ago = timezone.now() - timedelta(days=90)
        
        average_kpi_score_aggregation = KPIEvaluation.objects.filter(
            evaluatee=target_user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
            created_at__gte=three_months_ago
        ).aggregate(average_score=Avg('final_score'))
        
        average_kpi_score = average_kpi_score_aggregation.get('average_score') or 0

        summary_data = {
            "user": SubordinateSerializer(target_user, context={'request': request}).data,
            "task_performance": {
                "total_tasks": all_tasks.count(),
                "completed_count": completed_count,
                "active_count": all_tasks.filter(status__in=['TODO', 'IN_PROGRESS']).count(),
                "overdue_count": overdue_count,
                "average_kpi_score": round(average_kpi_score, 1),
                "priority_completion": list(done_tasks.values('priority').annotate(count=Count('id')).order_by('priority')),
            },
        }
        
        return Response(summary_data)
    
 
class KpiMonthlySummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug, *args, **kwargs):
        try:
            target_user = User.objects.get(slug=slug)
        except User.DoesNotExist:
            return Response({"detail": "İstifadəçi tapılmadı."}, status=status.HTTP_404_NOT_FOUND)

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date', timezone.now().strftime('%Y-%m-%d'))

        evaluations_query = KPIEvaluation.objects.filter(
            evaluatee=target_user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        )

        if start_date_str:
            evaluations_query = evaluations_query.filter(
                task__completed_at__date__range=[start_date_str, end_date_str]
            )
        else:
            try:
                year = int(request.query_params.get('year', datetime.now().year))
                month = int(request.query_params.get('month', datetime.now().month))
                evaluations_query = evaluations_query.filter(
                    task__completed_at__year=year,
                    task__completed_at__month=month
                )
            except (ValueError, TypeError):
                return Response({"detail": "İl və ay düzgün formatda deyil."}, status=status.HTTP_400_BAD_REQUEST)

        evaluations = evaluations_query.select_related('task').order_by('task__completed_at')

        evaluations_data = [
            {
                "day": evaluation.task.completed_at.day,
                "score": evaluation.final_score,
                "task_title": evaluation.task.title,
                "completed_at": evaluation.task.completed_at.isoformat() 
            }
            for evaluation in evaluations if evaluation.task.completed_at
        ]

        response_data = {
            'evaluations': evaluations_data,
        }
        return Response(response_data)
    

class UserKpiScoreView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug, *args, **kwargs):
        try:
            target_user = User.objects.get(slug=slug)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if not (request.user == target_user or request.user.role == 'admin' or request.user in target_user.get_all_superiors()):
             return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        three_months_ago = timezone.now() - timedelta(days=90)

        aggregation = KPIEvaluation.objects.filter(
            evaluatee=target_user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
            task__completed_at__gte=three_months_ago
        ).aggregate(average_score=Avg('final_score'))

        average_score = aggregation.get('average_score') or 0

        return Response({'average_kpi_score': round(average_score, 1)})