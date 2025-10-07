# performance/views.py

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Avg
from django.utils import timezone
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from .models import UserEvaluation
from .serializers import UserEvaluationSerializer, UserForEvaluationSerializer
from accounts.models import User
from django.db.models import Q

class UserEvaluationViewSet(viewsets.ModelViewSet):
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        İstifadəçinin görməyə icazəsi olan dəyərləndirmələri filtrləyir.
        - Admin hər şeyi görür.
        - Rəhbərlər özlərinin və tabeliyində olanların dəyərləndirmələrini görür.
        - İşçilər yalnız öz dəyərləndirmələrini görür.
        """
        user = self.request.user
        if user.is_staff or user.role == 'admin':
            return self.queryset

        # Bütün tabeliyində olanları tapmaq üçün bir yol
        subordinate_ids = [sub.id for sub in User.objects.all() if user in sub.get_all_superiors()]
        
        # İstifadəçinin özü və tabeliyində olanlar üçün filtrləmə
        allowed_view_ids = subordinate_ids + [user.id]

        return self.queryset.filter(evaluatee_id__in=allowed_view_ids)

    def perform_create(self, serializer):
        evaluatee = serializer.validated_data['evaluatee']
        serializer.save(evaluator=self.request.user, evaluatee=evaluatee)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        
        # Yalnız dəyərləndirməni edən rəhbər və ya Admin redaktə edə bilər
        if not (user.is_staff or user.role == 'admin') and instance.evaluator != user:
            raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")

        new_score = request.data.get('score')
        if new_score is None:
            return super().partial_update(request, *args, **kwargs) # Yalnız comment dəyişə bilər

        try:
            new_score = int(new_score)
            old_score = instance.score
            
            # Yalnız skor dəyişibsə tarixçəyə yaz
            if old_score != new_score:
                history_entry = {
                    "timestamp": timezone.now().isoformat(),
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
            # serializer.save() aşağıda çağırıldığı üçün burada save etmirik
        except (ValueError, TypeError):
            return Response({'score': 'Düzgün bir rəqəm daxil edin.'}, status=status.HTTP_400_BAD_REQUEST)
            
        return super().partial_update(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        """
        İstək göndərən rəhbərin birbaşa tabeliyində olan və 
        dəyərləndirə biləcəyi bütün işçilərin siyahısını qaytarır.
        Hər bir işçi üçün cari ayın dəyərləndirmə statusunu da əlavə edir.
        """
        evaluator = request.user
        
        # Admin bütün işçiləri (özü və top management xaric) dəyərləndirə bilər
        if evaluator.is_staff or evaluator.role == 'admin':
            subordinates = User.objects.filter(is_active=True).exclude(
                Q(id=evaluator.id) | Q(role='top_management')
            )
        else:
            # Bütün aktiv işçiləri gəzərək birbaşa rəhbəri `evaluator` olanları tapırıq
            all_users = User.objects.filter(is_active=True).exclude(id=evaluator.id)
            subordinates = [
                user for user in all_users if user.get_direct_superior() == evaluator
            ]

        # Serializer-ə `context` əlavə edərək cari ayın dəyərləndirməsini yoxlamaq olar
        # Amma biz bunu serializer-in öz daxilində etdik.
        serializer = UserForEvaluationSerializer(subordinates, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='performance-summary')
    def performance_summary(self, request):
        """
        Bir işçinin son 3, 6, 9, və 12 aylıq performans ortalamasını qaytarır.
        Query Param: ?evaluatee_id=<user_id>
        """
        evaluatee_id = request.query_params.get('evaluatee_id')
        if not evaluatee_id:
            return Response(
                {'error': 'evaluatee_id parametri tələb olunur.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        # --- İcazə Yoxlaması ---
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        today = timezone.now().date()
        summary = {
            'evaluatee_id': evaluatee.id,
            'evaluatee_name': evaluatee.get_full_name(),
            'averages': {}
        }
        
        periods = {'3 ay': 3, '6 ay': 6, '9 ay': 9, '1 il': 12}

        for label, months in periods.items():
            start_date = today - relativedelta(months=months)
            
            avg_data = UserEvaluation.objects.filter(
                evaluatee=evaluatee,
                evaluation_date__gte=start_date
            ).aggregate(
                average_score=Avg('score')
            )
            
            average = avg_data['average_score']
            summary['averages'][label] = round(average, 2) if average else None

        return Response(summary)