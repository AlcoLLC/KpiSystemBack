from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Exists, OuterRef
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email 
from accounts.models import User
from tasks.models import Task
from tasks.serializers import TaskSerializer
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            return self.queryset.select_related('task', 'evaluator', 'evaluatee')

        subordinate_ids = user.get_subordinates().values_list('id', flat=True)

        q_objects = Q(evaluatee=user) | Q(evaluator=user) | Q(evaluatee_id__in=subordinate_ids)
        
        return self.queryset.filter(q_objects).distinct().select_related('task', 'evaluator', 'evaluatee')

    def can_evaluate_user(self, evaluator, evaluatee):
        if evaluator == evaluatee:
            return False 
            
        if evaluatee.role == 'top_management':
            return False 
        direct_superior = evaluatee.get_direct_superior()
        
        if evaluator.role == 'admin':
            return True
            
        return direct_superior and direct_superior.id == evaluator.id

    def can_view_evaluation_results(self, viewer, evaluatee):
        if viewer == evaluatee or viewer.role == 'admin':
            return True

        all_superiors = evaluatee.get_all_superiors()
        if viewer in all_superiors:
            return True

        return False

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        if evaluatee.role == 'top_management':
            raise PermissionDenied("Top management tapşırıqları dəyərləndirilə bilməz.")

        if evaluator == evaluatee:
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq bir öz dəyərləndirmə etmisiniz.")

            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            
            try:
                logger.info(f"Rəhbərə KPI dəyərləndirmə sorğusu göndərilir: {instance.evaluatee.get_full_name()}")
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                logger.error(
                    f"KPI dəyərləndirmə e-poçtu göndərilərkən xəta baş verdi (Evaluatee ID: {instance.evaluatee.id}): {e}", 
                    exc_info=True
                )

            else:
                direct_superior = evaluatee.get_direct_superior()
                
                if not (direct_superior and direct_superior == evaluator) and not evaluator.role == 'admin':
                    raise PermissionDenied("Bu istifadəçini dəyərləndirməyə icazəniz yoxdur. Yalnız birbaşa rəhbər dəyərləndirmə edə bilər.")

                if not KPIEvaluation.objects.filter(
                    task=task, 
                    evaluatee=evaluatee, 
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists() and evaluator.role != 'admin':
                    raise ValidationError("Üst dəyərləndirmə etməzdən əvvəl işçinin öz dəyərləndirməsini tamamlaması lazımdır.")

                if KPIEvaluation.objects.filter(
                    task=task, 
                    evaluator=evaluator, 
                    evaluatee=evaluatee, 
                    evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                ).exists():
                    raise ValidationError("Bu tapşırığı bu işçi üçün artıq dəyərləndirmisiniz.")

                serializer.save(
                    evaluator=evaluator,
                    evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                )


    @action(detail=False, methods=['get'])
    def my_evaluations(self, request):
        user = request.user
        given_evaluations = self.get_queryset().filter(evaluator=user)
        received_evaluations = self.get_queryset().filter(evaluatee=user)
        return Response({
            'given': KPIEvaluationSerializer(given_evaluations, many=True).data,
            'received': KPIEvaluationSerializer(received_evaluations, many=True).data
        })

    @action(detail=False, methods=['get'], url_path='dashboard-tasks')
    def kpi_dashboard_tasks(self, request):
        user = request.user
        
        subordinate_ids = list(user.get_subordinates().values_list('id', flat=True))
        visible_user_ids = subordinate_ids + [user.id]

        tasks_to_show_q = Q(assignee_id__in=visible_user_ids)

        queryset = Task.objects.filter(
            tasks_to_show_q, status='DONE'
        ).exclude(assignee__role='top_management').select_related(
            'assignee', 'created_by'
        ).prefetch_related(
            'evaluations'
        ).distinct().order_by('-completed_at', '-created_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = TaskSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='pending-for-me')
    def my_subordinates_pending_evaluations(self, request):
        user = request.user
        
        all_active_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
        my_direct_subordinates_ids = [
            sub.id for sub in all_active_users if sub.get_direct_superior() == user
        ]

        if not my_direct_subordinates_ids and user.role != 'admin':
            return Response([])

        if user.role == 'admin':
            pending_tasks_q = Q(status='DONE')
        else:
            pending_tasks_q = Q(status='DONE', assignee_id__in=my_direct_subordinates_ids)

        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        my_superior_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
            evaluator=user
        )

        pending_for_me = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists),
            has_my_superior_eval=Exists(my_superior_eval_exists)
        ).filter(
            pending_tasks_q,
            has_self_eval=True,
            has_my_superior_eval=False
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee')

        serializer = TaskSerializer(pending_for_me, many=True, context={'request': request})
        return Response(serializer.data)
        
    @action(detail=False, methods=['get'])
    def task_evaluations(self, request):
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id parametri tələb olunur'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        evaluations = self.get_queryset().filter(task_id=task_id)
        
        filtered_evaluations = []
        for evaluation in evaluations:
            if self.can_view_evaluation_results(self.request.user, evaluation.evaluatee):
                filtered_evaluations.append(evaluation)
        
        return Response(KPIEvaluationSerializer(filtered_evaluations, many=True).data)

    @action(detail=False, methods=['get'])
    def evaluation_summary(self, request):
        task_id = request.query_params.get('task_id')
        evaluatee_id = request.query_params.get('evaluatee_id')
        
        if not task_id or not evaluatee_id:
            return Response({
                'error': 'task_id və evaluatee_id parametrləri tələb olunur'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı'}, status=status.HTTP_404_NOT_FOUND)
        
        if not self.can_view_evaluation_results(request.user, evaluatee):
            return Response({
                'error': 'Bu dəyərləndirmə nəticələrini görmə icazəniz yoxdur'
            }, status=status.HTTP_403_FORBIDDEN)
        
        evaluations = KPIEvaluation.objects.filter(
            task_id=task_id,
            evaluatee_id=evaluatee_id
        ).select_related('task', 'evaluator', 'evaluatee')
        
        self_evaluation = evaluations.filter(
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        ).first()
        
        superior_evaluation = evaluations.filter(
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        ).first()
        
        summary = {
            'task_id': task_id,
            'evaluatee_id': evaluatee_id,
            'self_evaluation': KPIEvaluationSerializer(self_evaluation).data if self_evaluation else None,
            'superior_evaluation': KPIEvaluationSerializer(superior_evaluation).data if superior_evaluation else None,
            'final_score': superior_evaluation.final_score if superior_evaluation else None,
            'is_complete': bool(self_evaluation and superior_evaluation)
        }
        
        return Response(summary)
    
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        new_score = request.data.get('score')
        new_comment = request.data.get('comment')

        is_self_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION
        is_superior_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION

        if instance.evaluator != user:
            raise PermissionDenied("Yalnız dəyərləndirməni yaradan şəxs redaktə edə bilər.")

        if is_self_eval:
            superior_eval_exists = KPIEvaluation.objects.filter(
                task=instance.task,
                evaluatee=instance.evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists()
            if superior_eval_exists:
                raise PermissionDenied("Rəhbər dəyərləndirməsi edildikdən sonra öz dəyərləndirmənizi redaktə edə bilməzsiniz.")

        old_score = None
        
        if new_score is not None:
            try:
                new_score = int(new_score)
                if is_self_eval:
                    old_score = instance.self_score
                    instance.self_score = new_score
                elif is_superior_eval:
                    old_score = instance.superior_score
                    instance.superior_score = new_score
            except (ValueError, TypeError):
                raise ValidationError({"score": "Düzgün bir rəqəm daxil edin."})

        if new_comment is not None:
            instance.comment = new_comment

        if old_score is not None and old_score != new_score:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "updated_by_id": user.id,
                "updated_by_name": user.get_full_name() or user.username,
                "previous_score": old_score,
                "new_score": new_score
            }
            if not isinstance(instance.history, list):
                instance.history = []
            instance.history.append(history_entry)
            instance.previous_score = old_score

        instance.updated_by = user
        instance.save()
        return Response(self.get_serializer(instance).data)
    
    @action(detail=False, methods=['get'], url_path='need-self-evaluation')
    def need_self_evaluation(self, request):
        user = request.user
        
        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluatee=user,
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        tasks = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists)
        ).filter(
            assignee=user,
            status='DONE',
            has_self_eval=False
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee', 'created_by').order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=False, methods=['get'], url_path='waiting-superior-evaluation')
    def waiting_superior_evaluation(self, request):
        user = request.user
        
        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluatee=user,
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        superior_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluatee=user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        )
        
        tasks = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists),
            has_superior_eval=Exists(superior_eval_exists)
        ).filter(
            assignee=user,
            status='DONE',
            has_self_eval=True,
            has_superior_eval=False
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee', 'created_by').order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=False, methods=['get'], url_path='i-evaluated')
    def i_evaluated(self, request):
        user = request.user
        
        evaluation_task_ids = KPIEvaluation.objects.filter(
            evaluator=user
        ).values_list('task_id', flat=True).distinct()
        
        tasks = Task.objects.filter(
            id__in=evaluation_task_ids,
            status='DONE'
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=False, methods=['get'], url_path='subordinates-need-evaluation')
    def subordinates_need_evaluation(self, request):
        user = request.user
        
        subordinate_ids = list(user.get_subordinates().values_list('id', flat=True))
        visible_user_ids = subordinate_ids + [user.id]
        
        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        superior_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        )
        
        tasks = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists),
            has_superior_eval=Exists(superior_eval_exists)
        ).filter(
            Q(assignee_id__in=visible_user_ids),
            status='DONE'
        ).exclude(
            Q(has_self_eval=True, has_superior_eval=True) |
            Q(assignee__role='top_management')
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='completed-evaluations')
    def completed_evaluations(self, request):
        user = request.user
        
        subordinate_ids = list(user.get_subordinates().values_list('id', flat=True))
        visible_user_ids = subordinate_ids + [user.id]

        evaluated_by_me_ids = KPIEvaluation.objects.filter(
            evaluator=user,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        ).values_list('task_id', flat=True)

        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        superior_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        )
        
        tasks = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists),
            has_superior_eval=Exists(superior_eval_exists)
        ).filter(
            assignee_id__in=visible_user_ids,
            status='DONE',
            has_self_eval=True,
            has_superior_eval=True
        ).exclude(
            id__in=evaluated_by_me_ids 
        ).exclude(
            assignee=user
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)