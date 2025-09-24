# kpis/views.py
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

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return KPIEvaluation.objects.all().select_related('task', 'evaluator', 'evaluatee')

        # User-in özü və tabeliyindəkilərin dəyərləndirmələri
        subordinates = self.get_user_subordinates(user)
        
        return KPIEvaluation.objects.filter(
            Q(evaluator=user) | Q(evaluatee=user) | Q(evaluatee__in=subordinates)
        ).distinct().select_related('task', 'evaluator', 'evaluatee')

    def get_direct_superior(self, employee):
        """
        İşçinin birbaşa rəhbərini tapır (departament əsasında hiyerarxik)
        """
        if not employee.department:
            return None
            
        if employee.role == 'top_management':
            return None  # Top management-in rəhbəri yoxdur
            
        if employee.role == 'employee':
            # Əvvəlcə eyni departamentdə manager axtarır
            manager = User.objects.filter(
                role='manager', 
                department=employee.department,
                is_active=True
            ).first()
            if manager:
                return manager
                
            # Manager yoxdursa department_lead axtarır
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=employee.department,
                is_active=True
            ).first()
            return dept_lead
            
        elif employee.role == 'manager':
            # Manager-in rəhbəri department_lead-dir
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=employee.department,
                is_active=True
            ).first()
            return dept_lead
            
        elif employee.role == 'department_lead':
            # Department lead-in rəhbəri top_management-dir
            top_mgmt = User.objects.filter(
                role='top_management',
                is_active=True
            ).first()
            return top_mgmt
            
        return None

    def can_evaluate_user(self, evaluator, evaluatee):
        """
        Sadəcə birbaşa rəhbər dəyərləndirə bilər (və admin)
        """
        if evaluator == evaluatee:
            return False
            
        if evaluator.role == 'admin':
            return evaluatee.role != 'top_management'  # Admin top management dəyərləndirə bilməz
        
        if evaluatee.role == 'top_management':
            return False  # Top management dəyərləndirmə olunmur
            
        # Birbaşa rəhbər yoxlaması
        direct_superior = self.get_direct_superior(evaluatee)
        return direct_superior and direct_superior.id == evaluator.id

    def can_view_evaluation_results(self, viewer, evaluatee):
        """
        Dəyərləndirmə nəticələrini kimler görə bilər
        """
        if viewer == evaluatee:
            return True  # Özünün nəticəsini görə bilər
            
        if viewer.role == 'admin':
            return True
            
        if evaluatee.role == 'top_management':
            return False  # Top management nəticələri görünmür
            
        # Birbaşa rəhbər və ya daha yüksək səviyyədə olanlar görə bilər
        if viewer.role == 'top_management':
            return True
            
        if (viewer.role == 'department_lead' and 
            evaluatee.department == viewer.department and
            evaluatee.role in ['manager', 'employee']):
            return True
            
        if (viewer.role == 'manager' and 
            evaluatee.department == viewer.department and
            evaluatee.role == 'employee'):
            return True
            
        return False

    def get_user_subordinates(self, user):
        """
        User-in görə biləcəyi işçiləri qaytarır
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

        # Top management taskları dəyərləndirmə olunmur
        if evaluatee.role == 'top_management':
            raise PermissionDenied("Top management taskları dəyərləndirmə olunmur.")

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
            # Üst dəyərləndirməsi - sadəcə birbaşa rəhbər
            if not self.can_evaluate_user(evaluator, evaluatee):
                raise PermissionDenied("Bu işçini dəyərləndirməyə icazəniz yoxdur. Sadəcə birbaşa rəhbər dəyərləndirə bilər.")

            # Admin istisnaları (admin öz dəyərləndirməsini tələb etmir)
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
        
        # Top management taskları istisna edilir
        user_completed_tasks = Task.objects.filter(
            assignee=user, 
            status='DONE'
        ).exclude(assignee__role='top_management')
        
        subordinates = self.get_user_subordinates(user)
        subordinate_tasks = Task.objects.filter(
            assignee__in=subordinates, 
            status='DONE'
        ).exclude(assignee__role='top_management')
        
        all_tasks = user_completed_tasks.union(subordinate_tasks).order_by('-created_at')
        
        all_tasks = all_tasks.select_related('assignee', 'created_by').prefetch_related(
            'evaluations__evaluator', 'evaluations__evaluatee'
        )

        return Response(TaskSerializer(all_tasks, many=True).data)

    @action(detail=False, methods=['get'])
    def my_subordinates_pending_evaluations(self, request):
        """
        Sadəcə birbaşa tabeliyimdəkilərin gözləyən dəyərləndirmələri
        """
        user = request.user
        
        # Birbaşa tabeliyindəkiləri tapır
        direct_subordinates = []
        if user.role == 'admin':
            direct_subordinates = User.objects.exclude(role='top_management')
        elif user.role == 'top_management':
            direct_subordinates = User.objects.filter(role='department_lead', is_active=True)
        elif user.role == 'department_lead':
            direct_subordinates = User.objects.filter(
                department=user.department,
                role='manager',
                is_active=True
            )
        elif user.role == 'manager':
            direct_subordinates = User.objects.filter(
                department=user.department,
                role='employee',
                is_active=True
            )
        
        pending = []
        
        tasks_with_evaluations = Task.objects.filter(
            status='DONE',
            assignee__in=direct_subordinates
        ).exclude(
            assignee__role='top_management'  # Top management istisnaları
        ).select_related('assignee').prefetch_related(
            Prefetch('evaluations', queryset=KPIEvaluation.objects.all(), to_attr='cached_evaluations')
        )
        
        for task in tasks_with_evaluations:
            evaluations = task.cached_evaluations
            has_self_eval = any(e.evaluation_type == 'SELF' for e in evaluations)
            has_my_superior_eval = any(
                e.evaluation_type == 'SUPERIOR' and e.evaluator == user for e in evaluations
            )

            # Öz dəyərləndirmə tamamlanıb və mənim dəyərləndirməm yoxdur
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
        
        # Görmə icazəsi yoxlaması
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
        
        # Görmə icazəsi yoxlaması
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