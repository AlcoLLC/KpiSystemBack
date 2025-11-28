from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .models import UserEvaluation
from .serializers import (
    UserEvaluationSerializer, 
    UserForEvaluationSerializer, 
    MonthlyScoreSerializer
)
from accounts.models import User

from reports.utils import create_log_entry
from reports.models import ActivityLog


class UserEvaluationViewSet(viewsets.ModelViewSet):
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role in ['admin', 'ceo']: 
            return self.queryset.order_by('-evaluation_date')

        q_objects = Q(evaluatee=user)

        subordinate_ids = user.get_user_kpi_subordinates().values_list('id', flat=True)
        if subordinate_ids:
            q_objects |= Q(evaluatee_id__in=subordinate_ids)
        
        return self.queryset.filter(q_objects).distinct().order_by('-evaluation_date')

    def perform_create(self, serializer):
        evaluation = serializer.save(evaluator=self.request.user)
        
        create_log_entry(
            actor=evaluation.evaluator,
            action_type=ActivityLog.ActionTypes.KPI_USER_EVALUATED,
            target_user=evaluation.evaluatee,
            details={
                'score': evaluation.score,
                'month': evaluation.evaluation_date.strftime('%Y-%m')
            }
        )


    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        evaluatee = instance.evaluatee

        is_admin = user.role == 'admin'
        
        if instance.evaluation_type == 'TOP_MANAGEMENT':
            if user.role == 'ceo':
                raise PermissionDenied("CEO Top Management dəyərləndirməsini redaktə edə bilməz.")
            
            if user.role == 'top_management':
                if instance.evaluator != user:
                    raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")
            elif not is_admin:
                raise PermissionDenied("Bu dəyərləndirməni yalnız Top Management və ya Admin redaktə edə bilər.")
        else:
            is_kpi_evaluator = evaluatee.get_kpi_evaluator() == user

            if not (is_admin or is_kpi_evaluator):
                raise PermissionDenied("Bu dəyərləndirməni yalnız işçinin birbaşa rəhbəri və ya Admin redaktə edə bilər.")
        
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        evaluator = request.user
        date_str = request.query_params.get('params[date]')
        department_id = request.query_params.get('params[department]')
        evaluation_status = request.query_params.get('evaluation_status') 

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            evaluation_date = timezone.now().date().replace(day=1)
        
        
        def get_all_subordinates_recursive(user):
            direct_subs = user.get_user_kpi_subordinates()
            all_subs = set(direct_subs)
            
            for sub in direct_subs:
                sub_subordinates = get_all_subordinates_recursive(sub)
                all_subs.update(sub_subordinates)
            
            return all_subs

        direct_subordinates = evaluator.get_user_kpi_subordinates()
        
        all_hierarchy_set = get_all_subordinates_recursive(evaluator)
        all_hierarchy_ids = {u.id for u in all_hierarchy_set}
        
        all_users_ids_to_check = all_hierarchy_ids | set(direct_subordinates.values_list('id', flat=True))
        
        base_users_qs = User.objects.filter(id__in=all_users_ids_to_check, is_active=True).exclude(
            role__in=['ceo', 'admin']
        ).distinct()

        if evaluator.role == 'admin' and department_id:
            try:
                dept_id = int(department_id)
                base_users_qs = base_users_qs.filter(
                    Q(department_id=dept_id) |  
                    Q(managed_department__id=dept_id) | 
                    Q(led_department__id=dept_id) |  
                    Q(top_managed_departments__id=dept_id) 
                ).distinct()
            except (ValueError, TypeError):
                pass

        if evaluation_status in ['evaluated', 'pending']:
             fully_evaluated_ids = UserEvaluation.objects.filter(
                 evaluation_date=evaluation_date,
                 evaluation_type=UserEvaluation.EvaluationType.SUPERIOR_EVALUATION
             ).filter(
                 evaluatee__received_user_evaluations__evaluation_date=evaluation_date,
                 evaluatee__received_user_evaluations__evaluation_type=UserEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
             ).values_list('evaluatee_id', flat=True).distinct()

             if evaluation_status == 'evaluated':
                 base_users_qs = base_users_qs.filter(id__in=fully_evaluated_ids)
             elif evaluation_status == 'pending':
                 base_users_qs = base_users_qs.exclude(id__in=fully_evaluated_ids)
        
        users_to_show = base_users_qs.select_related('department', 'position').order_by('last_name', 'first_name')

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(users_to_show, many=True, context=context)
        return Response(serializer.data)
    @action(detail=False, methods=['get'], url_path='my-performance-card')
    def my_performance_card(self, request):
        user = request.user
        date_str = request.query_params.get('date')

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            evaluation_date = timezone.now().date().replace(day=1)
        
        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(user, context=context)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        user = self.request.user
        if not (user.role in ['admin', 'ceo'] or user == evaluatee or user in evaluatee.get_kpi_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        scores = UserEvaluation.objects.filter(evaluatee=evaluatee).select_related('evaluator')

        if date_str:
            try:
                end_date = datetime.strptime(date_str, '%Y-%m').date()
                end_date = end_date + relativedelta(months=1) - relativedelta(days=1)
                scores = scores.filter(evaluation_date__lte=end_date)
            except ValueError:
                return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)

        scores = scores.order_by('-evaluation_date', 'evaluation_type')
        
        serializer = MonthlyScoreSerializer(scores, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='performance-summary')
    def performance_summary(self, request):
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        user = self.request.user
        if not (user.role in ['admin', 'ceo'] or user == evaluatee or user in evaluatee.get_kpi_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        try:
            end_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            end_date = timezone.now().date().replace(day=1)

        summary = {
            'evaluatee_id': evaluatee.id,
            'evaluatee_name': evaluatee.get_full_name(),
            'averages': {}
        }
        
        periods = {'3 ay': 3, '6 ay': 6, '9 ay': 9, '1 il': 12}

        base_query = UserEvaluation.objects.filter(
            evaluatee=evaluatee,
            evaluation_type=UserEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
        )

        for label, months in periods.items():
            start_date = end_date - relativedelta(months=(months-1))
            
            avg_data = base_query.filter(
                evaluation_date__gte=start_date,
                evaluation_date__lte=end_date
            ).aggregate(
                average_score=Avg('score')
            )
            
            average = avg_data['average_score']
            summary['averages'][label] = round(average, 2) if average else None

        return Response(summary)