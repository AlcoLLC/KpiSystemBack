from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Layihənizdəki modelləri və serializer-ləri import edin
from .models import UserEvaluation
from .serializers import (
    UserEvaluationSerializer, 
    UserForEvaluationSerializer, 
    MonthlyScoreSerializer
)
from accounts.models import User


class UserEvaluationViewSet(viewsets.ModelViewSet):
    """
    İstifadəçi Performans Dəyərləndirmələri (KPI) üçün API endpointləri.
    - Siyahı (GET): İstifadəçinin icazəsi olan bütün dəyərləndirmələri göstərir.
    - Yaratma (POST): Yeni bir dəyərləndirmə əlavə edir.
    - Redaktə (PATCH): Mövcud dəyərləndirməni qismən yeniləyir.
    - Silmə (DELETE): Bir dəyərləndirməni silir.
    """
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Görmə icazələrini tətbiq edir:
        - Admin hər şeyi görür.
        - İstifadəçilər öz dəyərləndirmələrini görür.
        - Rəhbərlər özlərinə tabe olan işçilərin dəyərləndirmələrini görür (KPI iyerarxiyasına görə).
        """
        user = self.request.user

        if user.role == 'admin':
            return self.queryset.order_by('-evaluation_date')

        # İstifadəçinin öz dəyərləndirmələri
        q_objects = Q(evaluatee=user)

        # Rəhbərin tabeçiliyində olanların dəyərləndirmələri (yeni metoda görə)
        subordinate_ids = user.get_kpi_subordinates().values_list('id', flat=True)
        if subordinate_ids:
            q_objects |= Q(evaluatee_id__in=subordinate_ids)
        
        return self.queryset.filter(q_objects).distinct().order_by('-evaluation_date')

    def perform_create(self, serializer):
        """Dəyərləndirməni yaradan şəxsi avtomatik təyin edir."""
        serializer.save(evaluator=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        """
        Redaktə icazələrini tətbiq edir:
        - Yalnız KPI iyerarxiyasındakı birbaşa rəhbər və ya Admin redaktə edə bilər.
        """
        instance = self.get_object()
        user = request.user
        evaluatee = instance.evaluatee

        is_admin = user.role == 'admin'
        # Yeni metoda görə yoxlama
        is_kpi_evaluator = evaluatee.get_kpi_evaluator() == user

        if not (is_admin or is_kpi_evaluator):
            raise PermissionDenied("Bu dəyərləndirməni yalnız işçinin birbaşa rəhbəri və ya Admin redaktə edə bilər.")
        
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        """
        İstifadəçinin KPI iyerarxiyasına görə dəyərləndirə biləcəyi işçilərin siyahısını qaytarır.
        """
        evaluator = request.user
        date_str = request.query_params.get('date')

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            evaluation_date = timezone.now().date().replace(day=1)
        
        # Bütün tabeçiliyində olanları al
        subordinates = evaluator.get_kpi_subordinates()

        # Ancaq bu siyahıdan yalnız birbaşa rəhbəri (evaluator) olanları seç
        evaluable_users_list = [
            user for user in subordinates if user.get_kpi_evaluator() == evaluator
        ]
        
        department_id = request.query_params.get('department')
        if department_id and evaluator.role == 'admin':
            try:
                evaluable_users_list = [user for user in evaluable_users_list if user.department_id == int(department_id)]
            except (ValueError, TypeError):
                pass

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(evaluable_users_list, many=True, context=context)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-performance-card')
    def my_performance_card(self, request):
        """Hazırki istifadəçinin öz performans kartını qaytarır."""
        user = request.user
        date_str = request.query_params.get('date')

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            evaluation_date = timezone.now().date().replace(day=1)
        
        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(user, context=context)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        """Seçilmiş işçinin aylıq skorlarını qaytarır."""
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        user = self.request.user
        # İcazə yoxlanışı: Admin, şəxsin özü və ya onun KPI rəhbərləri
        if not (user.role == 'admin' or user == evaluatee or user in evaluatee.get_kpi_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        scores = UserEvaluation.objects.filter(evaluatee=evaluatee)

        if date_str:
            try:
                end_date = datetime.strptime(date_str, '%Y-%m').date()
                end_date = end_date + relativedelta(months=1) - relativedelta(days=1)
                scores = scores.filter(evaluation_date__lte=end_date)
            except ValueError:
                return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)

        scores = scores.order_by('-evaluation_date')
        serializer = MonthlyScoreSerializer(scores, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='performance-summary')
    def performance_summary(self, request):
        """Seçilmiş işçinin 3, 6, 9, 12 aylıq ortalama performansını qaytarır."""
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        user = self.request.user
        if not (user.role == 'admin' or user == evaluatee or user in evaluatee.get_kpi_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        try:
            end_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except (ValueError, TypeError):
            end_date = timezone.now().date().replace(day=1)

        summary = {
            'evaluatee_id': evaluatee.id,
            'evaluatee_name': evaluatee.get_full_name(),
            'averages': {}
        }
        
        periods = {'3 ay': 3, '6 ay': 6, '9 ay': 9, '1 il': 12}

        for label, months in periods.items():
            start_date = end_date - relativedelta(months=(months-1))
            
            avg_data = UserEvaluation.objects.filter(
                evaluatee=evaluatee,
                evaluation_date__gte=start_date,
                evaluation_date__lte=end_date
            ).aggregate(
                average_score=Avg('score')
            )
            
            average = avg_data['average_score']
            summary['averages'][label] = round(average, 2) if average else None

        return Response(summary)