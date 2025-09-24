from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Prefetch
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email
from accounts.models import User
from tasks.models import Task
from tasks.serializers import TaskSerializer


class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    # kpi/views.py -> KPIEvaluationViewSet
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return KPIEvaluation.objects.all().select_related('task', 'evaluator', 'evaluatee')

        # Rəhbərin tabeliyində olan işçiləri tapırıq
        subordinates = self.get_user_subordinates(user)
        
        # Sorğunu genişləndiririk:
        # 1. User-in özünün daxil olduğu dəyərləndirmələr
        # 2. VƏ ya dəyərləndirilən şəxsin (evaluatee) user-in tabeliyində olduğu dəyərləndirmələr
        return KPIEvaluation.objects.filter(
            Q(evaluator=user) | Q(evaluatee=user) | Q(evaluatee__in=subordinates)
        ).distinct().select_related('task', 'evaluator', 'evaluatee')

    def find_evaluator_for_user(self, evaluatee):
        """
        Aynı departmandaki hiyerarşiye göre en yakın rəhbəri tapır
        """
        if evaluatee.role == 'top_management':
            return None
        
        if evaluatee.role == 'employee':
            manager = User.objects.filter(
                role='manager', 
                department=evaluatee.department
            ).first()
            if manager:
                return manager
                
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=evaluatee.department
            ).first()
            if dept_lead:
                return dept_lead
                
            return User.objects.filter(role='top_management').first()
            
        elif evaluatee.role == 'manager':
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=evaluatee.department
            ).first()
            if dept_lead:
                return dept_lead
                
            return User.objects.filter(role='top_management').first()
            
        elif evaluatee.role == 'department_lead':
            return User.objects.filter(role='top_management').first()
            
        return None

    def can_evaluate_user(self, evaluator, evaluatee):
        """
        Dəyərləndirici istifadəçini dəyərləndirə bilərmi yoxla - departman əsaslı
        """
        if evaluator == evaluatee:
            return False
            
        if evaluator.role == 'admin':
            return evaluatee.role != 'top_management'
        
        if evaluatee.role == 'top_management':
            return False
            
        if (evaluator.department != evaluatee.department and 
            evaluator.role not in ['admin', 'top_management']):
            return False
        
        role_hierarchy = {
            'employee': ['manager', 'department_lead', 'top_management'],
            'manager': ['department_lead', 'top_management'],
            'department_lead': ['top_management']
        }
        
        allowed_evaluators = role_hierarchy.get(evaluatee.role, [])
        return evaluator.role in allowed_evaluators

    def get_user_subordinates(self, user):
        """
        Kullanıcının alt seviyedeki işçilerini döndürür (aynı departmanda)
        """
        if user.role == 'admin':
            return User.objects.exclude(role='top_management')
        
        if user.role == 'top_management':
            return User.objects.exclude(role='top_management')
            
        if user.role == 'department_lead':
            return User.objects.filter(
                department=user.department,
                role__in=['manager', 'employee']
            )
            
        if user.role == 'manager':
            return User.objects.filter(
                department=user.department,
                role='employee'
            )
        
        return User.objects.none()

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        if evaluator == evaluatee:
            # Öz dəyərləndirməsi
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq öz dəyərləndirmənizi etmisiniz.")

            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            
            try:
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email göndəriləmədi: {str(e)}")

        else:
            # Üst dəyərləndirməsi
            if not self.can_evaluate_user(evaluator, evaluatee):
                raise PermissionDenied("Bu işçini dəyərləndirməyə icazəniz yoxdur.")

            if evaluator.role != 'admin':
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=evaluatee,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    raise ValidationError("Bu dəyərləndirməni etməzdən əvvəl işçi öz dəyərləndirməsini tamamlamalıdır.")

            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu işçini bu tapşırıq üçün artıq dəyərləndirmisiniz.")

            instance = serializer.save(
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

    @action(detail=False, methods=['get'])
    def kpi_dashboard_tasks(self, request):
        user = self.request.user
        
        # ... (user_completed_tasks və subordinate_tasks olduğu kimi qalır)
        user_completed_tasks = Task.objects.filter(assignee=user, status='DONE')
        subordinates = self.get_user_subordinates(user)
        subordinate_tasks = Task.objects.filter(assignee__in=subordinates, status='DONE')
        
        all_tasks = user_completed_tasks.union(subordinate_tasks).order_by('-created_at')
        
        # EFFEKTİVLİK ÜÇÜN prefetch_related ƏLAVƏ EDİLİR
        all_tasks = all_tasks.select_related('assignee', 'created_by').prefetch_related('evaluations__evaluator', 'evaluations__evaluatee')

        # TaskSerializer artıq evaluations sahəsini özü qaytaracaq
        return Response(TaskSerializer(all_tasks, many=True).data)

    @action(detail=False, methods=['get'])
    def my_subordinates_pending_evaluations(self, request):
        """
        Alt işçilərimin gözləyən dəyərləndirmələri.
        assigned_to -> assignee olaraq düzəldildi və N+1 problemi üçün optimallaşdırıldı.
        """
        user = request.user
        subordinates = self.get_user_subordinates(user)
        
        pending = []
        
        tasks_with_evaluations = Task.objects.filter(
            status='DONE',
            assignee__in=subordinates
        ).select_related('assignee').prefetch_related(
            Prefetch('evaluations', queryset=KPIEvaluation.objects.all(), to_attr='cached_evaluations')
        )
        
        for task in tasks_with_evaluations:
            if not self.can_evaluate_user(user, task.assignee):
                continue

            evaluations = task.cached_evaluations
            has_self_eval = any(e.evaluation_type == 'SELF' for e in evaluations)
            has_my_superior_eval = any(
                e.evaluation_type == 'SUPERIOR' and e.evaluator == user for e in evaluations
            )

            if (has_self_eval or user.role == 'admin') and not has_my_superior_eval:
                pending.append({
                    'task': TaskSerializer(task).data,
                    'evaluatee': {
                        'id': task.assignee.id,
                        'username': task.assignee.username,
                        'full_name': task.assignee.get_full_name(),
                        'role': task.assignee.role
                    }
                })
        
        return Response(pending)
        
    @action(detail=False, methods=['get'])
    def task_evaluations(self, request):
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id parametri tələb olunur'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        evaluations = self.get_queryset().filter(task_id=task_id)
        return Response(KPIEvaluationSerializer(evaluations, many=True).data)

    @action(detail=False, methods=['get'])
    def evaluation_summary(self, request):
        task_id = request.query_params.get('task_id')
        evaluatee_id = request.query_params.get('evaluatee_id')
        
        if not task_id or not evaluatee_id:
            return Response({
                'error': 'task_id və evaluatee_id parametrləri tələb olunur'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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