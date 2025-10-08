from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Exists, OuterRef
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email # Bu funksiyanın mövcud olduğunu güman edirik
from accounts.models import User
from tasks.models import Task
from tasks.serializers import TaskSerializer
from datetime import datetime


class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    # DƏYİŞİKLİK 1: `get_queryset` metodu `user.get_subordinates()` istifadə edərək sadələşdirildi.
    def get_queryset(self):
        """
        İstifadəçinin görməyə icazəsi olan dəyərləndirmələri siyahılayır:
        - Özünə aid olanlar (verdiyi və ya aldığı).
        - İyerarxik olaraq ona tabe olan işçilərin dəyərləndirmələri.
        """
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            return self.queryset.select_related('task', 'evaluator', 'evaluatee')

        # Modeldəki `get_subordinates` metodundan bütün tabeliyində olanları alırıq
        subordinate_ids = user.get_subordinates().values_list('id', flat=True)

        # Mənim özümə aid olan VƏ YA mənim tabeliyimdə olanlara aid olan dəyərləndirmələr
        q_objects = Q(evaluatee=user) | Q(evaluator=user) | Q(evaluatee_id__in=subordinate_ids)
        
        return self.queryset.filter(q_objects).distinct().select_related('task', 'evaluator', 'evaluatee')

    # DƏYİŞİKLİK 2: ViewSet içindəki bu metod artıq lazımsızdır. User modelindəki metod istifadə olunacaq.
    # def get_direct_superior(self, employee): ... (BU METOD SİLİNİR)

    def can_evaluate_user(self, evaluator, evaluatee):
        """
        Bir istifadəçinin digərini dəyərləndirib-dəyərləndirə bilməyəcəyini yoxlayır.
        """
        if evaluator == evaluatee:
            return False # Heç kim özünü (üst olaraq) dəyərləndirə bilməz
            
        if evaluatee.role == 'top_management':
            return False # Top management dəyərləndirilmir
            
        # DƏYİŞİKLİK 3: `User` modelindəki etibarlı metod çağırılır.
        direct_superior = evaluatee.get_direct_superior()
        
        if evaluator.role == 'admin':
            return True
            
        return direct_superior and direct_superior.id == evaluator.id

    def can_view_evaluation_results(self, viewer, evaluatee):
        """
        İstifadəçinin dəyərləndirmə nəticələrinə baxa biləcəyini yoxlayır.
        """
        if viewer == evaluatee or viewer.role == 'admin':
            return True

        # `get_all_superiors` metodu artıq User modelində olduğu üçün bu hissə düzgün işləyir.
        all_superiors = evaluatee.get_all_superiors()
        if viewer in all_superiors:
            return True

        return False
    
    # DƏYİŞİKLİK 4: Bu metod artıq lazımsızdır, çünki `user.get_subordinates()` var.
    # def get_user_subordinates(self, user): ... (BU METOD SİLİNİR)

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        if evaluatee.role == 'top_management':
            raise PermissionDenied("Top management tapşırıqları dəyərləndirilə bilməz.")

        # Öz Dəyərləndirmə Məntiqi
        if evaluator == evaluatee:
            if KPIEvaluation.objects.filter(
                task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq bir öz dəyərləndirmə etmisiniz.")

            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            # send_kpi_evaluation_request_email(instance) # E-mail göndərmə
        
        # Üst Dəyərləndirmə Məntiqi
        else:
            # `evaluatee.get_direct_superior()` metodu User modelindən çağırılır və düzgün işləyir.
            direct_superior = evaluatee.get_direct_superior()
            
            if not (direct_superior and direct_superior == evaluator) and not evaluator.role == 'admin':
                raise PermissionDenied("Bu istifadəçini dəyərləndirməyə icazəniz yoxdur. Yalnız birbaşa rəhbər dəyərləndirmə edə bilər.")

            if not KPIEvaluation.objects.filter(
                task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists() and evaluator.role != 'admin':
                raise ValidationError("Üst dəyərləndirmə etməzdən əvvəl işçinin öz dəyərləndirməsini tamamlaması lazımdır.")

            if KPIEvaluation.objects.filter(
                task=task, evaluator=evaluator, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırığı bu işçi üçün artıq dəyərləndirmisiniz.")

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

    # DƏYİŞİKLİK 5: `kpi_dashboard_tasks` metodu da `user.get_subordinates()` istifadə edərək yenidən yazıldı.
    @action(detail=False, methods=['get'], url_path='dashboard-tasks')
    def kpi_dashboard_tasks(self, request):
        """
        İstifadəçinin özünün və iyerarxik olaraq ona tabe olan hər kəsin
        tamamlanmış tapşırıqlarını və dəyərləndirmə statuslarını qaytarır.
        """
        user = request.user
        
        # Mən və mənim bütün tabeliyimdə olanlar
        subordinate_ids = list(user.get_subordinates().values_list('id', flat=True))
        visible_user_ids = subordinate_ids + [user.id]

        tasks_to_show_q = Q(assignee_id__in=visible_user_ids)

        queryset = Task.objects.filter(
            tasks_to_show_q, status='DONE'
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
        Hazırkı istifadəçinin (rəhbər) dəyərləndirməsini gözləyən tapşırıqları siyahılayır.
        """
        user = request.user
        
        # `get_direct_superior` metodu düzgün işlədiyi üçün bu məntiq dəyişməz qalır və düzgündür.
        all_active_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
        my_direct_subordinates_ids = [
            sub.id for sub in all_active_users if sub.get_direct_superior() == user
        ]

        if not my_direct_subordinates_ids and user.role != 'admin':
            return Response([])

        if user.role == 'admin':
            pending_tasks_q = Q(status='DONE')
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

        serializer = TaskSerializer(pending_for_me, many=True, context={'request': request})
        return Response(serializer.data)
        
    # (task_evaluations, evaluation_summary, partial_update metodları olduğu kimi qalır, çünki onlar artıq düzgün məntiqə əsaslanır)
    # ... digər action metodları ...
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

        if instance.evaluator != user:
            raise PermissionDenied("Yalnız dəyərləndirməni yaradan şəxs redaktə edə bilər.")

        if is_self_eval:
            superior_eval_exists = KPIEvaluation.objects.filter(
                task=instance.task,
                evaluatee=instance.evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists()
            if superior_eval_exists:
                raise PermissionDenied("Rəhbər dəyərləndirməsi edildikdən sonra öz dəyərləndirmənizi redaktə edə bilməzsiniz.")

        # --- UPDATE LOGIC ---
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
            instance.previous_score = old_score

        instance.updated_by = user
        instance.save()
        return Response(self.get_serializer(instance).data)