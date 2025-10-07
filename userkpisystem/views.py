from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Avg
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .models import UserEvaluation
from .serializers import UserEvaluationSerializer, UserForEvaluationSerializer, MonthlyScoreSerializer
from accounts.models import User
from django.db.models import Q

class UserEvaluationViewSet(viewsets.ModelViewSet):
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_staff or user.role == 'admin':
            return self.queryset.order_by('-evaluation_date')

        try:
            subordinate_ids = [sub.id for sub in User.objects.all() if user in sub.get_all_superiors()]
        except Exception:
            subordinate_ids = []

        if subordinate_ids:
            allowed_view_ids = subordinate_ids + [user.id]
            return self.queryset.filter(evaluatee_id__in=allowed_view_ids).order_by('-evaluation_date')
        
        return self.queryset.filter(evaluatee=user).order_by('-evaluation_date')

    def perform_create(self, serializer):
        evaluatee = serializer.validated_data['evaluatee']
        serializer.save(evaluator=self.request.user, evaluatee=evaluatee)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        
        if not (user.is_staff or user.role == 'admin') and instance.evaluator != user:
            raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")

        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        evaluator = request.user
        
        department_id = request.query_params.get('department')
        date_str = request.query_params.get('date')

        try:
            if date_str:
                evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1)
            else:
                evaluation_date = timezone.now().date().replace(day=1)
        except ValueError:
            return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)
        
        subordinates_qs = User.objects.filter(is_active=True)

        if evaluator.is_staff or evaluator.role == 'admin':
            subordinates = subordinates_qs.exclude(Q(id=evaluator.id) | Q(role='top_management'))
        else:
            all_users = subordinates_qs.exclude(id=evaluator.id)
            subordinates = [user for user in all_users if user.get_direct_superior() == evaluator]

        if department_id:
            subordinates = [user for user in subordinates if user.department_id == int(department_id)]

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(subordinates, many=True, context=context)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        """
        Bir işçinin bütün aylar üzrə aldığı qiymətlərin siyahısını qaytarır.
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

        # İcazə yoxlaması (Statistika ilə eyni məntiq)
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        # İşçiyə aid bütün dəyərləndirmələri tarixa görə sıralayırıq
        scores = UserEvaluation.objects.filter(
            evaluatee=evaluatee
        ).order_by('-evaluation_date')
        
        serializer = MonthlyScoreSerializer(scores, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='performance-summary')
    def performance_summary(self, request):
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
        