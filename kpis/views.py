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


class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Lists evaluations that the user is authorized to see:
        - Their own evaluations (given or received).
        - Evaluations of their hierarchical subordinates.
        """
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            return self.queryset.select_related('task', 'evaluator', 'evaluatee')

        # Base query for user's own evaluations
        q_objects = Q(evaluatee=user) | Q(evaluator=user)

        # Add subordinates' evaluations based on user's role and department
        if user.role == 'top_management':
            # Top Management can see all leads, managers, and employees
            q_objects |= Q(evaluatee__role__in=['department_lead', 'manager', 'employee'])
        
        elif user.role == 'department_lead' and user.department:
            # Department Leads can see all managers and employees in their department
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role__in=['manager', 'employee']
            )
        
        elif user.role == 'manager' and user.department:
            # Managers can see all employees in their department
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role='employee'
            )
        
        return self.queryset.filter(q_objects).distinct().select_related('task', 'evaluator', 'evaluatee')


    def get_direct_superior(self, employee):
        """
        İşçinin birbaşa rəhbərini tapır (departament əsasında hiyerarxik)
        Əgər eyni departamentdə birbaşa rəhbər yoxdursa, bir üst səviyyədə axtarır
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
            if dept_lead:
                return dept_lead
            
            # Department lead də yoxdursa top_management axtarır
            top_mgmt = User.objects.filter(
                role='top_management',
                is_active=True
            ).first()
            return top_mgmt
            
        elif employee.role == 'manager':
            # Manager-in rəhbəri department_lead-dir
            dept_lead = User.objects.filter(
                role='department_lead', 
                department=employee.department,
                is_active=True
            ).first()
            if dept_lead:
                return dept_lead
            
            # Department lead yoxdursa top_management
            top_mgmt = User.objects.filter(
                role='top_management',
                is_active=True
            ).first()
            return top_mgmt
            
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
        Sadəcə birbaşa rəhbər dəyərləndirə bilər
        """
        if evaluator == evaluatee:
            return False
            
        if evaluatee.role == 'top_management':
            return False  # Top management dəyərləndirmə olunmur
            
        # Birbaşa rəhbər yoxlaması
        direct_superior = self.get_direct_superior(evaluatee)
        
        # Admin istisna halda dəyərləndirə bilər (top_management istisna)
        if evaluator.role == 'admin' and evaluatee.role != 'top_management':
            return True
            
        return direct_superior and direct_superior.id == evaluator.id

    def can_view_evaluation_results(self, viewer, evaluatee):
        """
        Determines if a 'viewer' can see the evaluation results of an 'evaluatee'.
        A user can view results if they are:
        - The evaluatee themselves.
        - An admin.
        - Any user in the evaluatee's upward chain of command.
        """
        if viewer == evaluatee:
            return True  # Can see their own results

        if viewer.is_staff or viewer.role == 'admin':
            return True  # Admins can see everything

        # Check if the viewer is in the evaluatee's upward chain of command.
        all_superiors = evaluatee.get_all_superiors()
        if viewer in all_superiors:
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

        if evaluatee.role == 'top_management':
            raise PermissionDenied("Top management görevleri değerlendirilemez.")

        # Öz Değerlendirme Mantığı
        if evaluator == evaluatee:
            if KPIEvaluation.objects.filter(
                task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu görev için zaten bir öz değerlendirme yaptınız.")

            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            # Başarılı öz değerlendirme sonrası amire email gönder
            send_kpi_evaluation_request_email(instance)
        
        # Üst Değerlendirme Mantığı
        else:
            direct_superior = evaluatee.get_direct_superior()
            
            # Sadece DOĞRUDAN amir veya admin değerlendirme yapabilir
            if not (direct_superior and direct_superior == evaluator) and not evaluator.role == 'admin':
                raise PermissionDenied("Bu kullanıcıyı değerlendirme yetkiniz yok. Sadece doğrudan amir değerlendirme yapabilir.")

            # Üst değerlendirme için önce öz değerlendirme yapılmalı (admin hariç)
            if not KPIEvaluation.objects.filter(
                task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists() and evaluator.role != 'admin':
                raise ValidationError("Üst değerlendirme yapmadan önce çalışanın öz değerlendirmesini tamamlaması gerekir.")

            if KPIEvaluation.objects.filter(
                task=task, evaluator=evaluator, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu görevi bu çalışan için zaten değerlendirdiniz.")

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
        """
        Kullanıcının kendisinin ve hiyerarşik olarak altındaki herkesin 
        tamamlanmış görevlerini ve bunların değerlendirme durumlarını listeler.
        """
        user = request.user
        tasks_to_show = Q(assignee=user)

        role_hierarchy = ["employee", "manager", "department_lead", "top_management", "admin"]
        try:
            user_level = role_hierarchy.index(user.role)
            subordinate_roles = role_hierarchy[:user_level]
            
            # Departman filtresi (Admin ve Top Management hariç)
            if user.role in ['department_lead', 'manager']:
                tasks_to_show |= Q(assignee__role__in=subordinate_roles, assignee__department=user.department)
            elif user.role in ['admin', 'top_management']:
                 tasks_to_show |= Q(assignee__role__in=subordinate_roles)

        except (ValueError, AttributeError):
            pass

        queryset = Task.objects.filter(
            tasks_to_show, status='DONE'
        ).exclude(assignee__role='top_management').select_related(
            'assignee', 'created_by'
        ).prefetch_related(
            'evaluations'
        ).distinct().order_by('-completed_at', '-created_at')
        
        # Sayfalama uygula
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TaskSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='pending-for-me')
    def my_subordinates_pending_evaluations(self, request):
        """
        Mevcut kullanıcının (amir) değerlendirmesini bekleyen görevleri listeler.
        Bu, çalışanın öz değerlendirmesini yaptığı ancak amirin henüz değerlendirmediği görevlerdir.
        """
        user = request.user
        
        # Doğrudan astlarımı buluyorum
        subordinates = User.objects.filter(is_active=True).exclude(pk=user.pk)
        my_direct_subordinates_ids = [
            sub.id for sub in subordinates if sub.get_direct_superior() == user
        ]

        if not my_direct_subordinates_ids and user.role != 'admin':
            return Response([])

        # Admin tüm bekleyenleri görür (öz değerlendirme yapılmış olanlar)
        if user.role == 'admin':
            pending_tasks_q = Q(status='DONE')
        else:
            pending_tasks_q = Q(status='DONE', assignee_id__in=my_direct_subordinates_ids)

        # Alt sorgu: Bu görev için bir 'SELF' değerlendirme var mı?
        self_eval_exists = KPIEvaluation.objects.filter(
            task=OuterRef('pk'),
            evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
        )
        # Alt sorgu: Bu görev için BENİM tarafımdan yapılmış bir 'SUPERIOR' değerlendirme var mı?
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
            has_my_superior_eval=False # Benim değerlendirmem yok
        ).exclude(
            assignee__role='top_management'
        ).select_related('assignee')

        serializer = TaskSerializer(pending_for_me, many=True)
        return Response(serializer.data)
        
        
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
    
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        new_score = request.data.get('score')
        new_comment = request.data.get('comment')

        # --- PERMISSION CHECKS ---
        is_self_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION
        is_superior_eval = instance.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION

        # Rule: Only the original evaluator can edit their evaluation.
        if instance.evaluator != user:
            raise PermissionDenied("Yalnız dəyərləndirməni yaradan şəxs redaktə edə bilər.")

        # Rule: Self-evaluation can only be edited if a superior has not yet evaluated it.
        if is_self_eval:
            superior_eval_exists = KPIEvaluation.objects.filter(
                task=instance.task,
                evaluatee=instance.evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists()
            if superior_eval_exists:
                raise PermissionDenied("Rəhbər dəyərləndirməsi edildikdən sonra öz dəyərləndirmənizi redaktə edə bilməzsiniz.")

        # --- UPDATE LOGIC AND HISTORY LOGGING ---
        old_score = None
        
        if new_score is not None:
            try:
                new_score = int(new_score)
                # Determine which score field to update and get the old value
                if is_self_eval:
                    old_score = instance.self_score
                    instance.self_score = new_score
                elif is_superior_eval:
                    old_score = instance.superior_score
                    instance.superior_score = new_score
            except (ValueError, TypeError):
                raise ValidationError({"score": "Düzgün bir rəqəm daxil edin."})

        # Update comment if provided
        if new_comment is not None:
            instance.comment = new_comment

        # Create a history entry only if the score has actually changed
        if old_score is not None and old_score != new_score:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "updated_by_id": user.id,
                "updated_by_name": user.get_full_name() or user.username,
                "previous_score": old_score,
                "new_score": new_score
            }
            # Ensure history is a list before appending
            if not isinstance(instance.history, list):
                instance.history = []
            instance.history.append(history_entry)
            
            # --- START OF ADDED LOGIC ---
            # Also, update the dedicated previous_score field in the model.
            # Köhnə skoru xüsusi `previous_score` sahəsinə də əlavə edirik.
            instance.previous_score = old_score
            # --- END OF ADDED LOGIC ---

        # Record the user who made the update
        instance.updated_by = user
        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)