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

from reports.utils import create_log_entry
from reports.models import ActivityLog

logger = logging.getLogger(__name__)

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role in ['admin', 'ceo']: 
            return self.queryset.select_related('task', 'evaluator', 'evaluatee')

        subordinate_ids = user.get_subordinates().values_list('id', flat=True)
        q_objects = Q(evaluatee=user) | Q(evaluator=user) | Q(evaluatee_id__in=subordinate_ids)

        return self.queryset.filter(q_objects).distinct().select_related('task', 'evaluator', 'evaluatee')

    def can_evaluate_user(self, evaluator, evaluatee, evaluation_type):
        if evaluator == evaluatee:
            return True 
            
        if evaluator.role == 'admin':
            return True
        
        eval_config = evaluatee.get_evaluation_config_task()
        
        if evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
            return eval_config['superior_evaluator'] and eval_config['superior_evaluator'].id == evaluator.id
        
        elif evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
            if not eval_config['is_dual_evaluation']:
                return False
            return eval_config['tm_evaluator'] and eval_config['tm_evaluator'].id == evaluator.id
            
        return False

    def can_view_evaluation_results(self, viewer, evaluatee):
        if viewer == evaluatee or viewer.role in ['admin', 'ceo']: 
            return True

        all_superiors = evaluatee.get_all_superiors()
        if viewer in all_superiors:
            return True

        return False

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]
        
        eval_config = evaluatee.get_evaluation_config_task()
        
        if evaluator == evaluatee:
            if not eval_config['requires_self']:
                raise PermissionDenied("Bu rol özünü dəyərləndirə bilməz.")
            
            evaluation_type = KPIEvaluation.EvaluationType.SELF_EVALUATION
            
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=evaluation_type
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq bir öz dəyərləndirmə etmisiniz.")

            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            
            try:
                logger.info(f"Növbəti qiymətləndiriciyə KPI sorğusu göndərilir: {instance.evaluatee.get_full_name()}")
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                logger.error(f"KPI e-poçtu göndərilərkən xəta: {e}", exc_info=True)
        
        else:
            logger.info(f"Evaluator: {evaluator.get_full_name()} ({evaluator.role})")
            logger.info(f"Evaluatee: {evaluatee.get_full_name()} ({evaluatee.role})")
            logger.info(f"Superior Evaluator: {eval_config['superior_evaluator'].get_full_name() if eval_config['superior_evaluator'] else 'None'}")
            logger.info(f"TM Evaluator: {eval_config['tm_evaluator'].get_full_name() if eval_config['tm_evaluator'] else 'None'}")
            logger.info(f"Is Dual Evaluation: {eval_config['is_dual_evaluation']}")
            
            if evaluator.role == 'admin':
                evaluation_type = serializer.validated_data.get('evaluation_type')
            else:
                if eval_config['superior_evaluator'] and eval_config['superior_evaluator'].id == evaluator.id:
                    evaluation_type = KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                    logger.info(f"Təyin edilmiş evaluation_type: SUPERIOR_EVALUATION")
                elif eval_config['is_dual_evaluation'] and eval_config['tm_evaluator'] and eval_config['tm_evaluator'].id == evaluator.id:
                    evaluation_type = KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                    logger.info(f"Təyin edilmiş evaluation_type: TOP_MANAGEMENT_EVALUATION")
                else:
                    logger.error(f"Evaluator bu işçini qiymətləndirə bilməz!")
                    raise PermissionDenied("Bu işçini qiymətləndirməyə icazəniz yoxdur.")

            if not self.can_evaluate_user(evaluator, evaluatee, evaluation_type):
                raise PermissionDenied("Bu istifadəçini bu tip qiymətləndirmə ilə qiymətləndirməyə icazəniz yoxdur.")
            
            if not KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists() and evaluator.role != 'admin':
                raise ValidationError("Əvvəlcə işçinin öz dəyərləndirməsi tamamlanmalıdır.")

            if evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
                if not KPIEvaluation.objects.filter(
                    task=task, 
                    evaluatee=evaluatee, 
                    evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                ).exists() and evaluator.role != 'admin':
                    raise ValidationError("Top Management qiymətləndirməsi üçün SUPERIOR dəyərləndirməsi tamamlanmalıdır.")

            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=evaluation_type
            ).exists():
                raise ValidationError(f"Bu tapşırıq üçün artıq {evaluation_type} qiymətləndirməsi etmisiniz.")

            instance = serializer.save(evaluator=evaluator, evaluation_type=evaluation_type)
            
            if instance.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION and eval_config['is_dual_evaluation']:
                try:
                    logger.info(f"Top Management-ə KPI sorğusu göndərilir: {instance.evaluatee.get_full_name()}")
                    send_kpi_evaluation_request_email(instance) 
                except Exception as e:
                    logger.error(f"TM e-poçtu göndərilərkən xəta: {e}", exc_info=True)

        if instance:
            score = instance.self_score if instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION else instance.superior_score or instance.top_management_score
            create_log_entry(
                actor=evaluator,
                action_type=ActivityLog.ActionTypes.KPI_TASK_EVALUATED,
                target_user=evaluatee,
                target_task=task,
                details={
                    'task_title': task.title,
                    'score': score,
                    'evaluation_type': instance.get_evaluation_type_display()
                }
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
        
        if user.role in ['admin', 'ceo']:
            visible_user_ids = list(User.objects.filter(is_active=True).exclude(role__in=['ceo', 'admin']).values_list('id', flat=True))
            tasks_to_show_q = Q(assignee_id__in=visible_user_ids)
        else:
            subordinate_ids = list(user.get_subordinates().values_list('id', flat=True))
            visible_user_ids = subordinate_ids + [user.id]
            tasks_to_show_q = Q(assignee_id__in=visible_user_ids)
        
        if user.role not in ['admin', 'ceo', 'top_management']:
             tasks_to_show_q &= ~Q(assignee__role='top_management')

        queryset = Task.objects.filter(
            tasks_to_show_q, status='DONE'
        ).select_related(
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
    @action(detail=False, methods=['get'], url_path='pending-for-me')
    def my_subordinates_pending_evaluations(self, request):
        user = request.user
        
        # 1. Bütün aktiv istifadəçilər
        all_active_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
        
        # 2. Cari istifadəçinin qiymətləndirməli olduğu istifadəçilər və qiymətləndirmə növləri
        users_to_evaluate_map = {} # {evaluatee_id: [eval_type1, eval_type2]}
        
        for sub in all_active_users:
            if sub.role in ['admin', 'ceo']:
                continue
            
            eval_config = sub.get_evaluation_config_task()
            
            if eval_config['superior_evaluator'] and eval_config['superior_evaluator'].id == user.id:
                users_to_evaluate_map.setdefault(sub.id, []).append(KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION)
            
            if eval_config['tm_evaluator'] and eval_config['tm_evaluator'].id == user.id:
                users_to_evaluate_map.setdefault(sub.id, []).append(KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION)

        # Admin hər kəsi qiymətləndirə bilər (Superior və TM), lakin CEO yalnız Top Management-ı.
        if user.role == 'admin':
            all_ids = all_active_users.exclude(role__in=['admin', 'ceo']).values_list('id', flat=True)
            for uid in all_ids:
                users_to_evaluate_map.setdefault(uid, []).extend([
                    KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION, 
                    KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                ])
        elif user.role == 'ceo':
            tm_ids = User.objects.filter(role='top_management', is_active=True).values_list('id', flat=True)
            for uid in tm_ids:
                users_to_evaluate_map.setdefault(uid, []).append(KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION)

        evaluable_ids = users_to_evaluate_map.keys()

        if not evaluable_ids:
            return Response([])
        
        # 3. Taskları tapmaq
        pending_tasks = Task.objects.filter(status='DONE', assignee_id__in=evaluable_ids)
        
        final_pending_tasks = []
        for task in pending_tasks:
            evaluatee_id = task.assignee_id
            eval_types_to_do = users_to_evaluate_map.get(evaluatee_id, [])
            
            # İlkin şərtlər (Self Evaluation)
            has_self_eval = KPIEvaluation.objects.filter(
                task=task,
                evaluatee_id=evaluatee_id,
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists()
            
            if not has_self_eval and evaluatee_id != user.id and user.role != 'admin': # Admin yoxlayırsa, öz dəyərləndirməyə ehtiyac yoxdur.
                 continue

            is_pending = False
            for eval_type in eval_types_to_do:
                
                # Superior dəyərləndirmə gözlənilirsə
                if eval_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                    if not KPIEvaluation.objects.filter(
                        task=task,
                        evaluator=user,
                        evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                    ).exists():
                        is_pending = True
                        break
                
                # Top Management dəyərləndirmə gözlənilirsə (Superior tamamlandıqdan sonra)
                elif eval_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
                    superior_exists = KPIEvaluation.objects.filter(
                        task=task,
                        evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                    ).exists()
                    
                    if superior_exists and not KPIEvaluation.objects.filter(
                        task=task,
                        evaluator=user,
                        evaluation_type=KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                    ).exists():
                        is_pending = True # Bu, taskı "Məndən gözlənilən" siyahısına salır
                        break
                    
            if is_pending:
                final_pending_tasks.append(task)
                
        # Nəticə Task objeleri olaraq qaytarılır
        serializer = TaskSerializer(final_pending_tasks, many=True, context={'request': request})
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
        
        top_management_evaluation = evaluations.filter(
            evaluation_type=KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
        ).first()
        
        eval_config = evaluatee.get_evaluation_config_task()
        
        final_score = None
        if eval_config['is_dual_evaluation']:
            if top_management_evaluation and top_management_evaluation.top_management_score is not None:
                final_score = top_management_evaluation.top_management_score
                logger.info(f"[evaluation_summary] Dual eval: Final score = TOP_MANAGEMENT score = {final_score}")
            else:
                logger.info(f"[evaluation_summary] Dual eval: TOP_MANAGEMENT score yoxdur")
        else:
            if superior_evaluation and superior_evaluation.superior_score is not None:
                final_score = superior_evaluation.superior_score
                logger.info(f"[evaluation_summary] Non-dual eval: Final score = SUPERIOR score = {final_score}")
            else:
                logger.info(f"[evaluation_summary] Non-dual eval: SUPERIOR score yoxdur")
        
        if eval_config['is_dual_evaluation']:
            is_complete = bool(
                self_evaluation and 
                superior_evaluation and 
                top_management_evaluation and
                top_management_evaluation.top_management_score is not None
            )
        else:
            is_complete = bool(
                self_evaluation and 
                superior_evaluation and
                superior_evaluation.superior_score is not None
            )
        
        summary = {
            'task_id': task_id,
            'evaluatee_id': evaluatee_id,
            'self_evaluation': KPIEvaluationSerializer(self_evaluation).data if self_evaluation else None,
            'superior_evaluation': KPIEvaluationSerializer(superior_evaluation).data if superior_evaluation else None,
            'top_management_evaluation': KPIEvaluationSerializer(top_management_evaluation).data if top_management_evaluation else None,
            'final_score': final_score,
            'is_complete': is_complete,
            'evaluation_config': {
                'is_dual_evaluation': eval_config['is_dual_evaluation'],
                'superior_evaluator': eval_config['superior_evaluator'].get_full_name() if eval_config['superior_evaluator'] else None,
                'superior_evaluator_id': eval_config['superior_evaluator_id'],
                'tm_evaluator': eval_config['tm_evaluator'].get_full_name() if eval_config['tm_evaluator'] else None,
                'tm_evaluator_id': eval_config['tm_evaluator_id'],
            }
        }

        return Response(summary)
        
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        new_score = request.data.get('score')
        new_comment = request.data.get('comment')
        attachment = request.data.get('attachment')

        is_admin = user.is_staff or user.role == 'admin'

        is_self_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION
        is_superior_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        is_top_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
        
        if instance.evaluator != user and not is_admin:
            raise PermissionDenied("Yalnız dəyərləndirməni yaradan şəxs və ya administrator redaktə edə bilər.")

        # Self evaluation-da Superior dəyərləndirmə varsa, yalnız admin dəyişə bilər
        if is_self_eval:
            superior_eval_exists = KPIEvaluation.objects.filter(
                task=instance.task,
                evaluatee=instance.evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists()
            if superior_eval_exists and user.role not in ['admin', 'ceo']: 
                raise PermissionDenied("Rəhbər dəyərləndirməsi edildikdən sonra öz dəyərləndirmənizi redaktə edə bilməzsiniz (yalnız administrator/CEO dəyişə bilər).")
        
        # Superior evaluation-da TM dəyərləndirmə varsa, yalnız admin dəyişə bilər
        if is_superior_eval:
            # DÜZƏLDILDI: get_evaluation_config_task() istifadə et
            eval_config = instance.evaluatee.get_evaluation_config_task()
            if eval_config['is_dual_evaluation']:
                tm_eval_exists = KPIEvaluation.objects.filter(
                    task=instance.task,
                    evaluatee=instance.evaluatee,
                    evaluation_type=KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                ).exists()
                if tm_eval_exists and user.role not in ['admin', 'ceo']:
                    raise PermissionDenied("Top Management dəyərləndirməsi edildikdən sonra Superior dəyərləndirməsini redaktə edə bilməzsiniz (yalnız administrator/CEO dəyişə bilər).")
        
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
                elif is_top_eval:
                    old_score = instance.top_management_score
                    instance.top_management_score = new_score
            except (ValueError, TypeError):
                raise ValidationError({"score": "Düzgün bir rəqəm daxil edin."})

        if 'comment' in request.data:
            new_comment = request.data.get('comment')
            
            if new_comment and new_comment.strip():
                instance.comment = new_comment.strip()
            else:
                instance.comment = None

        if 'attachment' in request.data:
            new_attachment = request.data.get('attachment')
            if new_attachment:
                if instance.attachment:
                    instance.attachment.delete(save=False)
                instance.attachment = new_attachment
            else:
                if instance.attachment:
                    instance.attachment.delete(save=False)
                instance.attachment = None

        # History əlavə et
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
        
        if user.role in ['ceo', 'admin']:
            return Response([])
        
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
            Q(assignee=user) &
            Q(status='DONE') &
            Q(has_self_eval=True) &
            Q(has_superior_eval=False)
        ).exclude(
            assignee__role__in=['ceo', 'admin']
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
            Q(assignee=user) | Q(assignee__role__in=['ceo', 'admin'])
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='subordinates-need-evaluation')
    def subordinates_need_evaluation(self, request):
        user = request.user
        
        if user.role == 'ceo':
             subordinate_ids = list(user.get_kpi_subordinates().values_list('id', flat=True))
        else:
             subordinate_ids = list(user.get_kpi_subordinates().values_list('id', flat=True))

        visible_user_ids = subordinate_ids + [user.id]
        
        tasks_q = Q(assignee_id__in=visible_user_ids) & Q(status='DONE')

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
            tasks_q
        ).exclude(
            Q(has_self_eval=True, has_superior_eval=True) | 
            Q(assignee__role__in=['ceo', 'admin'])
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='completed-evaluations')
    def completed_evaluations(self, request):
        user = request.user
        
        if user.role == 'ceo':
             subordinate_ids = list(user.get_kpi_subordinates().values_list('id', flat=True))
        else:
             subordinate_ids = list(user.get_kpi_subordinates().values_list('id', flat=True))

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
            Q(assignee_id__in=visible_user_ids) &
            Q(status='DONE') &
            Q(has_self_eval=True) & 
            Q(has_superior_eval=True)
        ).exclude(
            id__in=evaluated_by_me_ids 
        ).exclude(
            assignee=user
        ).exclude(
            assignee__role__in=['ceo', 'admin']
        ).select_related('assignee', 'created_by').prefetch_related(
            'evaluations'
        ).order_by('-completed_at')
        
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)