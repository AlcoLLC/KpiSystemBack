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
            # Admin bütün dəyərləndirmə növlərini edə bilər
            return True
        
        # --- 1. SUPERIOR_EVALUATION üçün icazə (Manager/Lead) ---
        if evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
            # Əgər TM Superior Evaluation edirsə, bu yalnız D-Lead üçün keçərli olmalıdır.
            if evaluator.role == 'top_management':
                # TM yalnız D-Lead-i SUPERIOR kimi qiymətləndirə bilər.
                return evaluatee.role == 'department_lead' and evaluatee.department and evaluatee.department in evaluator.top_managed_departments.all()
            
            # Manager/Lead üçün normal superior yoxlaması
            kpi_evaluator = evaluatee.get_kpi_evaluator() 
            return kpi_evaluator and kpi_evaluator.id == evaluator.id
        
        # --- 2. TOP_MANAGEMENT_EVALUATION üçün icazə (Top Management) ---
        elif evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
            # Bu, Manager/Employee üçün üçüncü mərhələdir.
            if evaluator.role == 'top_management' and evaluatee.role in ['manager', 'employee']:
                if evaluatee.department and evaluatee.department in evaluator.top_managed_departments.all():
                    return True
                return False
            
            # Başqa rollar TOP_MANAGEMENT_EVALUATION edə bilməz
            return False
            
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
        
        # evaluation_type API-dən gəlir, lakin Admin rolundan fərqli olaraq, 
        # digər rəhbərlər üçün bu dəyəri öz roluna uyğun məcburi şəkildə təyin edirik.
        evaluation_type_from_api = serializer.validated_data.get('evaluation_type')
        
        # 1. ÖZ DƏYƏRLƏNDİRMƏSİ (SELF_EVALUATION)
        if evaluator == evaluatee:
            # Admin ve CEO kendini değerlendiremez
            if evaluator.role in ['admin', 'ceo']: 
                raise PermissionDenied("Admin və ya CEO özünü dəyərləndirə bilməz.")
            
            evaluation_type = KPIEvaluation.EvaluationType.SELF_EVALUATION
            
            # Aynı task için zaten self evaluation var mı kontrol et
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
            
            # Rəhbərə bildiriş göndər
            try:
                logger.info(f"Rəhbərə KPI dəyərləndirmə sorğusu göndərilir: {instance.evaluatee.get_full_name()}")
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                logger.error(
                    f"KPI dəyərləndirmə e-poçtu göndərilərkən xəta baş verdi (Evaluatee ID: {instance.evaluatee.id}): {e}", 
                    exc_info=True
                )
        
        # 2. ÜST DƏYƏRLƏNDİRMƏSİ (SUPERIOR/TOP MANAGEMENT)
        else:
            
            # Dəyərləndirənin roluna görə Evaluation Type-ı məcburi təyin et (TM-in SUPERIOR etməsinin qarşısını alır)
            if evaluator.role == 'top_management':
                # TM D-Lead-i SUPERIOR, Manager/Employee-u TOP_MANAGEMENT edir
                if evaluatee.role == 'department_lead':
                    evaluation_type = KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                elif evaluatee.role in ['manager', 'employee']:
                    evaluation_type = KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                else:
                    raise PermissionDenied("Top Management yalnız D-Lead, Manager və Employee'u dəyərləndirə bilər.")
            elif evaluator.role in ['manager', 'department_lead']:
                # Manager/Lead həmişə SUPERIOR_EVALUATION etməlidir
                evaluation_type = KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            elif evaluator.role == 'ceo' or evaluator.role == 'admin':
                # Admin/CEO icazəli tiplərdən birini göndərməlidir (API-dən gələn dəyəri istifadə edirik)
                evaluation_type = evaluation_type_from_api
            else:
                # Başqa rolların başqasını qiymətləndirməsinə icazə yoxdur
                raise PermissionDenied("Bu rol ilə başqasını dəyərləndirməyə icazəniz yoxdur.")

            # Yekun Evaluation Type-ın keçərli olmasını təmin et
            if evaluation_type not in [KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION, KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION]:
                raise ValidationError("Dəyərləndirmə tipi qeyri-qanunidir və ya rolunuza uyğun deyil.")

            # TM tərəfindən yalnız Manager və Employee qiymətləndirilə bilər (can_evaluate_user-da yoxlanılır)
            if evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION and evaluatee.role not in ['manager', 'employee'] and evaluator.role != 'admin':
                 raise PermissionDenied("Yuxarı İdarəetmə yalnız Manager və ya Employee'u dəyərləndirə bilər.")

            # İcazə kontrolü (məcburi təyin edilmiş evaluation_type'ı ötürürük)
            if not self.can_evaluate_user(evaluator, evaluatee, evaluation_type): 
                raise PermissionDenied("Bu istifadəçini dəyərləndirməyə icazəniz yoxdur. Yalnız təyin edilmiş rəhbər dəyərləndirmə edə bilər.")
            
            # Self evaluation tamamlanma tələbi kontrolu (Admin/CEO istisna)
            if evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION and evaluator.role != 'admin':
                
                # 1. Self Evaluation mövcud olmalıdır
                if not KPIEvaluation.objects.filter(
                    task=task, 
                    evaluatee=evaluatee, 
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                     raise ValidationError("Top Management qiymətləndirməsi üçün işçinin öz dəyərləndirməsi tamamlanmalıdır.")

                # 2. Superior Evaluation mövcud olmalıdır
                if not KPIEvaluation.objects.filter(
                    task=task, 
                    evaluatee=evaluatee, 
                    evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                ).exists():
                    raise ValidationError("Top Management qiymətləndirməsi üçün Üst Rəhbər (Superior) dəyərləndirməsi tamamlanmalıdır.")

            # Aynı üst dəyərləndirmənin mövcudluğunu yoxla
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=evaluation_type
            ).exists():
                raise ValidationError(f"Bu tapşırığı bu işçi üçün artıq {evaluation_type} dəyərləndirməsi ilə qiymətləndirmisiniz.")

            instance = serializer.save(evaluator=evaluator, evaluation_type=evaluation_type)
            
            # SUPERIOR_EVALUATION tamamlandıqda Top Management-ə bildiriş göndər
            if instance.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                 try:
                    logger.info(f"Top Management-ə KPI dəyərləndirmə sorğusu göndərilir: {instance.evaluatee.get_full_name()}")
                    send_kpi_evaluation_request_email(instance) 
                 except Exception as e:
                    logger.error(
                        f"Top Management KPI dəyərləndirmə e-poçtu göndərilərkən xəta baş verdi (Evaluatee ID: {instance.evaluatee.id}): {e}", 
                        exc_info=True
                    )

        # Log kaydı
        if instance:
            score = instance.self_score if instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION else instance.superior_score
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

    # kpi/views.py (və ya kpi_evaluation_app-in views.py faylı)

# ... (Əvvəlki kod) ...

    @action(detail=False, methods=['get'], url_path='pending-for-me')
    def my_subordinates_pending_evaluations(self, request):
        user = request.user
        
        all_active_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
        my_direct_subordinates_ids = []
        pending_tasks_q = Q()
        
        if user.role == 'ceo':
            my_direct_subordinates_ids = list(all_active_users.filter(role='top_management').values_list('id', flat=True))
            pending_tasks_q = Q(status='DONE', assignee_id__in=my_direct_subordinates_ids)

        elif user.role == 'admin':
            pending_tasks_q = Q(status='DONE') & ~Q(assignee__role__in=['admin', 'ceo']) 
        else:
            # SUPERIOR və ya TOP_MANAGEMENT kimi qiymətləndirə biləcəyi istifadəçiləri tapır
            for sub in all_active_users:
                # SUPERIOR Dəyərləndirici (Manager, Department Lead)
                # Buraya CEO-nun TM-i qiymətləndirməsi də daxildir.
                if sub.get_kpi_evaluator() == user:
                    my_direct_subordinates_ids.append(sub.id)
                
                # TOP_MANAGEMENT Dəyərləndirici
                if user.role == 'top_management' and sub.role in ['manager', 'employee']:
                    if sub.department and sub.department in user.top_managed_departments.all():
                        if sub.id not in my_direct_subordinates_ids:
                            my_direct_subordinates_ids.append(sub.id)
            
            if my_direct_subordinates_ids:
                pending_tasks_q = Q(status='DONE', assignee_id__in=my_direct_subordinates_ids)
            
        if not pending_tasks_q:
            return Response([])

        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        # İstifadəçinin roluna uyğun olaraq gözləyən qiymətləndirmə tipini yoxlayır
        if user.role == 'ceo':
            # CEO, TM-i SUPERIOR kimi qiymətləndirir
            my_eval_exists = KPIEvaluation.objects.filter(
                task=OuterRef('pk'),
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
                evaluator=user
            )
        elif user.role == 'top_management':
            # Top Management, Manager/Employee'u TOP_MANAGEMENT_EVALUATION kimi, 
            # D-Lead-i SUPERIOR_EVALUATION kimi qiymətləndirir.
            my_eval_exists = KPIEvaluation.objects.filter(
                task=OuterRef('pk'),
                evaluator=user,
                evaluation_type__in=[
                    KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION, 
                    KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
                ]
            )
        elif user.role in ['manager', 'department_lead']:
            # Manager, Department Lead SUPERIOR_EVALUATION kimi qiymətləndirir
            my_eval_exists = KPIEvaluation.objects.filter(
                task=OuterRef('pk'),
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION,
                evaluator=user
            )
        else:
            # Admin rolunu burada daha sadə yoxlaya bilərik (Admin hər şeyi edə bilər, 
            # lakin digər TM/CEO qiymətləndirmələrini yoxlamalıyıq)
            # Admin üçün əlavə yoxlama. Hər hansı bir dəyərləndirmə etdiyi halda artıq pending olmamalıdır
            my_eval_exists = KPIEvaluation.objects.filter(
                task=OuterRef('pk'),
                evaluator=user
            )

        
        pending_for_me = Task.objects.annotate(
            has_self_eval=Exists(self_eval_exists),
            has_my_eval=Exists(my_eval_exists) # my_eval_exists istifadə edirik
        ).filter(
            pending_tasks_q,
            has_self_eval=True, 
            has_my_eval=False # Mənim tərəfimdən hələ qiymətləndirilməyib
        ).exclude(
            Q(assignee__role__in=['admin', 'ceo'])
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
        
        # YENİ: Top Management Evaluation qeydini tap
        top_management_evaluation = evaluations.filter(
            evaluation_type=KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION
        ).first()
        
        # Yekun skoru təyin etmə məntiqi: Top Management qiymətləndirməsi varsa, onu götür, əks halda Superior qiymətləndirməsini.
        final_eval = top_management_evaluation or superior_evaluation
        final_score = final_eval.final_score if final_eval else None
        
        # is_complete şərtini yeniləyirik: Top Management qiymətləndirməsi varsa, tamamlanmış sayılır.
        is_complete = bool(self_evaluation and (superior_evaluation and not top_management_evaluation) or top_management_evaluation)
        
        # YENİ: Top Management qiymətləndirməsini də cavaba əlavə et
        summary = {
            'task_id': task_id,
            'evaluatee_id': evaluatee_id,
            'self_evaluation': KPIEvaluationSerializer(self_evaluation).data if self_evaluation else None,
            'superior_evaluation': KPIEvaluationSerializer(superior_evaluation).data if superior_evaluation else None,
            'top_management_evaluation': KPIEvaluationSerializer(top_management_evaluation).data if top_management_evaluation else None, # YENİ ƏLAVƏ
            'final_score': final_score,
            'is_complete': is_complete
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

        if is_self_eval:
            superior_eval_exists = KPIEvaluation.objects.filter(
                task=instance.task,
                evaluatee=instance.evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists()
            if superior_eval_exists and user.role not in ['admin', 'ceo']: 
                raise PermissionDenied("Rəhbər dəyərləndirməsi edildikdən sonra öz dəyərləndirmənizi redaktə edə bilməzsiniz (yalnız administrator/CEO dəyişə bilər).")
            
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
        
        # CEO ve Admin kendini değerlendirmez, diğer rollerin taskları gösterilir
        if user.role in ['ceo', 'admin']:
            return Response([])
        
        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluatee=user,
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        
        # TÜM ROLLER İÇİN (admin/ceo hariç) self evaluation gösterilir
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