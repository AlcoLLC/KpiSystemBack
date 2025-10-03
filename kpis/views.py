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

        # Departman bazlı filtreleme
        if user.role in ['department_lead', 'manager']:
            subordinate_evaluations &= Q(evaluatee__department=user.department)

        return self.queryset.filter(own_evaluations | subordinate_evaluations).distinct().select_related('task', 'evaluator', 'evaluatee')

    # ------------------ KALDIRILAN METODLAR ------------------
    # Bu ViewSet içindeki get_direct_superior, can_evaluate_user, 
    # can_view_evaluation_results ve get_user_subordinates metodları kaldırıldı.
    # Çünkü bu mantıklar ya doğrudan User modelindeki metodlarla ya da
    # DRF'in kendi permission sistemiyle daha temiz yönetilebilir.
    # ---------------------------------------------------------

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
            # === DEĞİŞİKLİK BURADA ===
            # User modelindeki get_direct_superior metodu ile doğru amiri buluyoruz.
            # Bu metod, istediğiniz fallback mantığını (manager->lead->top_management) zaten içeriyor.
            direct_superior = evaluatee.get_direct_superior()
            
            # Sadece DOĞRUDAN amir veya admin değerlendirme yapabilir
            if not (direct_superior and direct_superior == evaluator) and not evaluator.is_staff:
                raise PermissionDenied("Bu kullanıcıyı değerlendirme yetkiniz yok. Sadece doğrudan amir veya yönetici değerlendirme yapabilir.")

            # Üst değerlendirme için önce öz değerlendirme yapılmalı (admin hariç)
            if not KPIEvaluation.objects.filter(
                task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists() and not evaluator.is_staff:
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
        user = request.user
        tasks_to_show = Q(assignee=user)

        # Admin ve Top Management herkesi görür
        if user.is_staff or user.role == 'top_management':
            tasks_to_show |= Q() # Hepsini dahil et
        # Department Lead, kendi departmanındaki manager ve employee'leri görür
        elif user.role == 'department_lead':
             tasks_to_show |= Q(assignee__department=user.department, assignee__role__in=['manager', 'employee'])
        # Manager, kendi departmanındaki employee'leri görür
        elif user.role == 'manager':
            tasks_to_show |= Q(assignee__department=user.department, assignee__role='employee')

        queryset = Task.objects.filter(
            tasks_to_show, status='DONE'
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
        """
        Mevcut kullanıcının (amir) değerlendirmesini bekleyen görevleri listeler.
        Bu, çalışanın öz değerlendirmesini yaptığı ancak amirin henüz değerlendirmediği görevlerdir.
        """
        user = request.user
        
        # === DEĞİŞİKLİK BURADA ===
        # Bütün aktif kullanıcıları alıp, `get_direct_superior` metodu bizim mevcut
        # kullanıcımızı döndürüyorsa, o kişi bizim doğrudan astımızdır (fallback dahil).
        all_active_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
        
        my_direct_subordinates_ids = [
            subordinate.id 
            for subordinate in all_active_users 
            if subordinate.get_direct_superior() == user
        ]
        
        # Eğer admin ise, değerlendirmesi gereken herkesi listeye dahil et
        if user.is_staff:
            pending_tasks_q = Q(status='DONE')
        elif not my_direct_subordinates_ids:
            return Response([])
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

        serializer = TaskSerializer(pending_for_me, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def task_evaluations(self, request):
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id parametri tələb olunur'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            task = Task.objects.get(pk=task_id)
            evaluatee = task.assignee
        except Task.DoesNotExist:
            return Response({'error': 'Tapşırıq tapılmadı'}, status=status.HTTP_404_NOT_FOUND)

        # Görmə icazəsi yoxlaması
        # Basit bir kontrol: Admin, değerlendiren, değerlendirilen veya değerlendirilenin amiri görebilir.
        superior = evaluatee.get_direct_superior()
        if not (request.user.is_staff or request.user == evaluatee or request.user == superior):
             raise PermissionDenied("Bu dəyərləndirmə nəticələrini görməyə icazəniz yoxdur.")

        evaluations = self.get_queryset().filter(task_id=task_id)
        return Response(KPIEvaluationSerializer(evaluations, many=True).data)

    @action(detail=False, methods=['get'])
    def evaluation_summary(self, request):
        task_id = request.query_params.get('task_id')
        evaluatee_id = request.query_params.get('evaluatee_id')
        
        if not task_id or not evaluatee_id:
            return Response({'error': 'task_id və evaluatee_id parametrləri tələb olunur'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı'}, status=status.HTTP_404_NOT_FOUND)
        
        superior = evaluatee.get_direct_superior()
        if not (request.user.is_staff or request.user == evaluatee or request.user == superior):
            raise PermissionDenied("Bu dəyərləndirmə nəticələrini görməyə icazəniz yoxdur.")
        
        evaluations = KPIEvaluation.objects.filter(task_id=task_id, evaluatee_id=evaluatee_id)
        
        self_evaluation = evaluations.filter(evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION).first()
        superior_evaluation = evaluations.filter(evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION).first()
        
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

        # Rule: Only the original evaluator can edit their evaluation.
        if instance.evaluator != user:
            raise PermissionDenied("Yalnız dəyərləndirməni yaradan şəxs redaktə edə bilər.")

        # Rule: Self-evaluation can only be edited if a superior has not yet evaluated it.
        if instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
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
                if instance.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
                    old_score = instance.self_score
                    instance.self_score = new_score
                else: # SUPERIOR_EVALUATION
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

        instance.updated_by = user
        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)