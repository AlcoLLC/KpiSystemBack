from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email
from accounts.models import User

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return KPIEvaluation.objects.all().select_related('task', 'evaluator', 'evaluatee')
        
        return KPIEvaluation.objects.filter(
            Q(evaluator=user) | Q(evaluatee=user)
        ).select_related('task', 'evaluator', 'evaluatee')

    def find_evaluator_for_user(self, evaluatee):
        """
        Aynı departmandaki hiyerarşiye göre en yakın rəhbəri tapır
        """
        if evaluatee.role == 'top_management':
            return None  # top_management-i heç kim dəyərləndirmir
        
        # Prioritet sırası: birbaşa üst → aynı departmandaki üst
        if evaluatee.role == 'employee':
            # Aynı departmanda manager axtarırıq
            manager = User.objects.filter(
                role='manager', 
                department=evaluatee.department
            ).first()
            if manager:
                return manager
                
            # Aynı departmanda department_lead axtarırıq
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=evaluatee.department
            ).first()
            if dept_lead:
                return dept_lead
                
            # Son çare olaraq top_management
            return User.objects.filter(role='top_management').first()
            
        elif evaluatee.role == 'manager':
            # Manager üçün department_lead axtarırıq
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=evaluatee.department
            ).first()
            if dept_lead:
                return dept_lead
                
            # Son çare olaraq top_management
            return User.objects.filter(role='top_management').first()
            
        elif evaluatee.role == 'department_lead':
            # Department_lead üçün yalnız top_management
            return User.objects.filter(role='top_management').first()
            
        return None

    def can_evaluate_user(self, evaluator, evaluatee):
        """
        Dəyərləndirici istifadəçini dəyərləndirə bilərmi yoxla - departman əsaslı
        """
        # Döngü önlemek için temel kontroller
        if evaluator == evaluatee:
            return False  # Kendini değerlendirmek için farklı mantık var
            
        if evaluator.role == 'admin':
            # Admin yalnız top_management xaric hamını dəyərləndirə bilər
            return evaluatee.role != 'top_management'
        
        if evaluatee.role == 'top_management':
            return False  # Heç kim top_management-i dəyərləndirmir
            
        # Aynı departmanda olmaları şərti (admin ve top_management istisna)
        if (evaluator.department != evaluatee.department and 
            evaluator.role not in ['admin', 'top_management']):
            return False
        
        # Hiyerarxiya qaydaları - sadece direkt üst seviyelere izin
        role_hierarchy = {
            'employee': ['manager', 'department_lead', 'top_management'],
            'manager': ['department_lead', 'top_management'],
            'department_lead': ['top_management']
        }
        
        allowed_evaluators = role_hierarchy.get(evaluatee.role, [])
        return evaluator.role in allowed_evaluators

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

            # Admin xaric üçün, öz dəyərləndirməsi tamamlanmalıdır
            if evaluator.role != 'admin':
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=evaluatee,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    raise ValidationError("Bu dəyərləndirməni etməzdən əvvəl işçi öz dəyərləndirməsini tamamlamalıdır.")

            # Təkrar dəyərləndirməni yoxla
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
    def pending_evaluations(self, request):
        from tasks.models import Task
        
        user = request.user
        
        completed_tasks = Task.objects.filter(
            status='DONE'
        ).select_related('assigned_to')
        
        pending = []
        
        for task in completed_tasks:
            if not task.assigned_to:
                continue
                
            can_evaluate = False
            evaluation_type = None
            
            # Öz dəyərləndirməsi kontrolu
            if task.assigned_to == user:
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=user,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    can_evaluate = True
                    evaluation_type = 'SELF'
            
            else:
                # Üst dəyərləndirməsi kontrolu
                if self.can_evaluate_user(user, task.assigned_to):
                    has_self_eval = KPIEvaluation.objects.filter(
                        task=task,
                        evaluatee=task.assigned_to,
                        evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                    ).exists()
                    
                    has_superior_eval = KPIEvaluation.objects.filter(
                        task=task,
                        evaluator=user,
                        evaluatee=task.assigned_to,
                        evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                    ).exists()
                    
                    # Admin istisna olmaqla, öz dəyərləndirmə şərtidir
                    if (has_self_eval or user.role == 'admin') and not has_superior_eval:
                        can_evaluate = True
                        evaluation_type = 'SUPERIOR'
            
            if can_evaluate:
                from tasks.serializers import TaskSerializer
                pending.append({
                    'task': TaskSerializer(task).data,
                    'evaluation_type': evaluation_type
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
        
        return summary

    @action(detail=False, methods=['get'])
    def my_subordinates_pending_evaluations(self, request):
        from tasks.models import Task
        
        user = request.user
        pending = []
        
        # Bütün tamamlanmış tapşırıqları götür
        completed_tasks = Task.objects.filter(
            status='DONE'
        ).select_related('assigned_to')
        
        for task in completed_tasks:
            if task.assigned_to and self.can_evaluate_user(user, task.assigned_to):
                has_self_eval = KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=task.assigned_to,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists()
                
                has_my_superior_eval = KPIEvaluation.objects.filter(
                    task=task,
                    evaluator=user,
                    evaluatee=task.assigned_to,
                    evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
                ).exists()
                
                if (has_self_eval or user.role == 'admin') and not has_my_superior_eval:
                    from tasks.serializers import TaskSerializer
                    pending.append({
                        'task': TaskSerializer(task).data,
                        'evaluatee': {
                            'id': task.assigned_to.id,
                            'username': task.assigned_to.username,
                            'full_name': task.assigned_to.get_full_name(),
                            'role': task.assigned_to.role
                        }
                    })
        
        return Response(pending)