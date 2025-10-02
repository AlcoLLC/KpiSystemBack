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
        """
        Kullanıcının sadece görme yetkisi olan değerlendirmeleri listeler.
        """
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            return self.queryset.select_related('task', 'evaluator', 'evaluatee')

        # Hiyerarşik olarak altındaki herkesin ve kendi değerlendirmelerini görebilir.
        role_hierarchy = ["employee", "manager", "department_lead", "top_management", "admin"]
        try:
            user_level = role_hierarchy.index(user.role)
        except ValueError:
            user_level = -1
        
        allowed_roles_to_view = role_hierarchy[:user_level]

        # Kullanıcının kendi değerlendirmeleri
        own_evaluations = Q(evaluatee=user) | Q(evaluator=user)
        
        # Astlarının değerlendirmeleri (Rol bazlı)
        subordinate_evaluations = Q(evaluatee__role__in=allowed_roles_to_view)

        return self.queryset.filter(own_evaluations | subordinate_evaluations).distinct().select_related('task', 'evaluator', 'evaluatee')


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
        Dəyərləndirmə nəticələrini kimler görə bilər:
        - Özü
        - Admin
        - Bütün üst rollarda olanlar (birbaşa rəhbərdən yuxarı hiyerarxiyada)
        """
        if viewer == evaluatee:
            return True  # Özünün nəticəsini görə bilər
            
        if viewer.role == 'admin':
            return True
            
        if evaluatee.role == 'top_management':
            return False  # Top management nəticələri görünmür
            
        # Top management hər şeyi görə bilər
        if viewer.role == 'top_management':
            return True
            
        # Department lead öz departamentindəki manager və employee-ləri görə bilər
        if viewer.role == 'department_lead':
            if evaluatee.department == viewer.department and evaluatee.role in ['manager', 'employee']:
                return True
            # Digər departamentlərdəki department lead-ləri də görə bilər
            if evaluatee.role == 'department_lead':
                return True
                
        # Manager öz departamentindəki employee-ləri görə bilər
        if viewer.role == 'manager':
            if evaluatee.department == viewer.department and evaluatee.role == 'employee':
                return True
            # Digər departamentlərdəki manager və employee-ləri də görə bilər
            if evaluatee.role in ['manager', 'employee']:
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