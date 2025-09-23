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

    def can_evaluate_user(self, evaluator, evaluatee):
        """
        Departamenta görə hiyerarxik dəyərləndirmə qaydalarını yoxla
        """
        if evaluator.role == 'admin':
            # Admin yalnız top_management xaric hamını dəyərləndirə bilər
            return evaluatee.role != 'top_management'
        
        # Eyni departamentdə olmalıdırlar (NULL departament da daxil)
        if evaluator.department != evaluatee.department:
            return False
        
        # top_management-i heç kim dəyərləndirmir
        if evaluatee.role == 'top_management':
            return False
            
        # Hiyerarxiya qaydaları departamentdə
        if evaluatee.role == 'employee':
            return evaluator.role in ['manager', 'department_lead', 'top_management']
        elif evaluatee.role == 'manager':
            return evaluator.role in ['department_lead', 'top_management']
        elif evaluatee.role == 'department_lead':
            return evaluator.role == 'top_management'
        
        return False

    def get_preferred_evaluator_for_user(self, evaluatee):
        """
        İstifadəçi üçün departamentindəki birbaşa üstü tap
        """
        if evaluatee.role == 'top_management':
            return None
            
        department = evaluatee.department
        
        # Hiyerarxik sıralama departamentdə
        if evaluatee.role == 'employee':
            # İlk manager axtarırıq eyni departamentdə
            evaluator = User.objects.filter(
                role='manager', 
                department=department
            ).first()
            if evaluator:
                return evaluator
            
            # Manager yoxdursa department_lead axtarırıq
            evaluator = User.objects.filter(
                role='department_lead', 
                department=department
            ).first()
            if evaluator:
                return evaluator
            
            # Heç biri yoxdursa top_management
            evaluator = User.objects.filter(role='top_management').first()
            return evaluator
            
        elif evaluatee.role == 'manager':
            # İlk department_lead axtarırıq eyni departamentdə
            evaluator = User.objects.filter(
                role='department_lead', 
                department=department
            ).first()
            if evaluator:
                return evaluator
            
            # Yoxdursa top_management
            evaluator = User.objects.filter(role='top_management').first()
            return evaluator
            
        elif evaluatee.role == 'department_lead':
            # Yalnız top_management
            evaluator = User.objects.filter(role='top_management').first()
            return evaluator
        
        return None

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
                raise PermissionDenied("Bu işçini dəyərləndirməyə icazəniz yoxdur. Eyni departamentdə olmalı və hiyerarxiya qaydalarına uygun olmalısınız.")

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
            can_evaluate = False
            evaluation_type = None
            
            if task.assigned_to == user:
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=user,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    can_evaluate = True
                    evaluation_type = 'SELF'
            
            else:
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
        
        return Response(summary)

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
                            'role': task.assigned_to.role,
                            'department': task.assigned_to.department.name if task.assigned_to.department else 'Departament təyin edilməyib'
                        }
                    })
        
        return Response(pending)

    @action(detail=False, methods=['get'])
    def can_evaluate(self, request):
        """
        İstifadəçinin hansı işçiləri dəyərləndirə biləcəyini yoxla
        """
        user = request.user
        evaluable_users = []
        
        if user.role == 'admin':
            # Admin top_management xaric hamını dəyərləndirə bilər
            users = User.objects.exclude(role='top_management').exclude(id=user.id)
        else:
            # Departamentindəki alt səviyyədəki istifadəçiləri tap
            department = user.department
            users = User.objects.filter(department=department).exclude(id=user.id)
        
        for potential_evaluatee in users:
            if self.can_evaluate_user(user, potential_evaluatee):
                evaluable_users.append({
                    'id': potential_evaluatee.id,
                    'username': potential_evaluatee.username,
                    'full_name': potential_evaluatee.get_full_name(),
                    'role': potential_evaluatee.role,
                    'department': potential_evaluatee.department.name if potential_evaluatee.department else None
                })
        
        return Response(evaluable_users)