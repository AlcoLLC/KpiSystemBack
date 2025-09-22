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
    # Add the queryset attribute at class level
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter evaluations based on user permissions"""
        user = self.request.user
        
        # Admin can see all evaluations
        if user.role == 'admin':
            return KPIEvaluation.objects.all().select_related('task', 'evaluator', 'evaluatee')
        
        # Users can see evaluations where they are evaluator or evaluatee
        return KPIEvaluation.objects.filter(
            Q(evaluator=user) | Q(evaluatee=user)
        ).select_related('task', 'evaluator', 'evaluatee')

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        # Self-evaluation logic
        if evaluator == evaluatee:
            # Check if self-evaluation already exists
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq öz dəyərləndirmənizi etmisiniz.")

            # Create self-evaluation
            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            
            # Send email to superior after self-evaluation
            try:
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                # Log error but don't fail the evaluation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email göndəriləmədi: {str(e)}")

        else:
            # Superior evaluation logic
            ROLE_HIERARCHY = {
                "employee": 1,
                "manager": 2,
                "department_lead": 3,
                "top_management": 4,
                "admin": 5
            }

            evaluator_level = ROLE_HIERARCHY.get(evaluator.role, 0)
            evaluatee_level = ROLE_HIERARCHY.get(evaluatee.role, 0)

            # Check if evaluator has permission to evaluate
            if evaluator_level <= evaluatee_level and evaluator.role != 'admin':
                raise PermissionDenied("Yalnız özünüzdən aşağı rolda olan işçiləri dəyərləndirə bilərsiniz.")

            # Check if self-evaluation exists (except for admin)
            if evaluator.role != 'admin':
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=evaluatee,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    raise ValidationError("Bu dəyərləndirməni etməzdən əvvəl işçi öz dəyərləndirməsini tamamlamalıdır.")

            # Check if superior evaluation already exists
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu işçini bu tapşırıq üçün artıq dəyərləndirmisiniz.")

            # Create superior evaluation
            serializer.save(
                evaluator=evaluator,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            )

    @action(detail=False, methods=['get'])
    def my_evaluations(self, request):
        """Get evaluations for current user (given and received)"""
        user = request.user
        
        given_evaluations = self.get_queryset().filter(evaluator=user)
        received_evaluations = self.get_queryset().filter(evaluatee=user)
        
        return Response({
            'given': KPIEvaluationSerializer(given_evaluations, many=True).data,
            'received': KPIEvaluationSerializer(received_evaluations, many=True).data
        })

    @action(detail=False, methods=['get'])
    def pending_evaluations(self, request):
        """Get tasks that need evaluation by current user"""
        from tasks.models import Task
        
        user = request.user
        
        # Get completed tasks that need evaluation
        completed_tasks = Task.objects.filter(
            status='DONE'
        ).select_related('assigned_to')
        
        pending = []
        
        for task in completed_tasks:
            # Check if user can evaluate this task
            can_evaluate = False
            evaluation_type = None
            
            # Self evaluation check
            if task.assigned_to == user:
                if not KPIEvaluation.objects.filter(
                    task=task,
                    evaluatee=user,
                    evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
                ).exists():
                    can_evaluate = True
                    evaluation_type = 'SELF'
            
            # Superior evaluation check
            else:
                ROLE_HIERARCHY = {
                    "employee": 1,
                    "manager": 2,
                    "department_lead": 3,
                    "top_management": 4,
                    "admin": 5
                }
                
                user_level = ROLE_HIERARCHY.get(user.role, 0)
                assignee_level = ROLE_HIERARCHY.get(task.assigned_to.role if task.assigned_to else 0, 0)
                
                if user_level > assignee_level or user.role == 'admin':
                    # Check if self-evaluation exists and superior evaluation doesn't
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
        """Get all evaluations for a specific task"""
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id parametri tələb olunur'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        evaluations = self.get_queryset().filter(task_id=task_id)
        return Response(KPIEvaluationSerializer(evaluations, many=True).data)