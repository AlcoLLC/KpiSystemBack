from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .models import UserEvaluation
from .serializers import UserEvaluationSerializer, UserForEvaluationSerializer, MonthlyScoreSerializer
from accounts.models import User

class UserEvaluationViewSet(viewsets.ModelViewSet):
    """
    İstifadəçi performans dəyərləndirmələrini rol və sərt departament məntiqi ilə idarə edir.
    """
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        - Admin hər şeyi görür.
        - Digər bütün rollar (Top Management daxil olmaqla) yalnız öz və öz departamentindəki
          astlarının dəyərləndirmələrini görür.
        """
        user = self.request.user

        if user.is_staff or user.role == 'admin':
            return self.queryset.order_by('-evaluation_date')

        # Hər bir istifadəçi mütləq öz dəyərləndirməsini görür.
        q_objects = Q(evaluatee=user)

        # Admin olmayan bütün rollar üçün departament məhdudiyyəti tətbiq edilir.
        if user.department:
            if user.role == 'top_management':
                # Top Management öz departamentindəki bütün aşağı rolları görür.
                q_objects |= Q(evaluatee__department=user.department, evaluatee__role__in=['department_lead', 'manager', 'employee'])
            elif user.role == 'department_lead':
                q_objects |= Q(evaluatee__department=user.department, evaluatee__role__in=['manager', 'employee'])
            elif user.role == 'manager':
                q_objects |= Q(evaluatee__department=user.department, evaluatee__role='employee')
        
        return self.queryset.filter(q_objects).distinct().order_by('-evaluation_date')

    def perform_create(self, serializer):
        evaluatee = serializer.validated_data['evaluatee']
        serializer.save(evaluator=self.request.user, evaluatee=evaluatee)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        evaluatee = instance.evaluatee
        is_admin = user.is_staff or user.role == 'admin'
        is_direct_superior = evaluatee.get_direct_superior() == user
        if not (is_admin or is_direct_superior):
            raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə yalnız birbaşa rəhbər və ya Admin icazəlidir.")
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        """
        - Admin, top management xaricində hər kəsi dəyərləndirə bilər.
        - Digər bütün rollar yalnız öz departamentindəki astlarını dəyərləndirə bilər.
        """
        evaluator = request.user
        department_id = request.query_params.get('department')
        date_str = request.query_params.get('date')

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except ValueError:
            return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)
        
        subordinates = User.objects.none()

        if evaluator.is_staff or evaluator.role == 'admin':
            subordinates = User.objects.filter(is_active=True).exclude(Q(id=evaluator.id) | Q(role='top_management'))
        
        elif evaluator.department: # Departament, admin olmayan bütün digər rollar üçün mütləqdir
            base_department_qs = User.objects.filter(is_active=True, department=evaluator.department).exclude(id=evaluator.id)
            if evaluator.role == 'top_management':
                subordinates = base_department_qs.filter(role__in=['department_lead', 'manager', 'employee'])
            elif evaluator.role == 'department_lead':
                subordinates = base_department_qs.filter(role__in=['manager', 'employee'])
            elif evaluator.role == 'manager':
                subordinates = base_department_qs.filter(role='employee')

        # Adminin öz siyahısını departamentə görə filtrləməsi üçün
        if department_id and (evaluator.is_staff or evaluator.role == 'admin'):
            subordinates = subordinates.filter(department_id=int(department_id))

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(subordinates, many=True, context=context)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-performance-card')
    def my_performance_card(self, request):
        """
        Daxil olmuş istifadəçinin öz performans kartı məlumatlarını qaytarır.
        Frontend-dəki "Mənim Performansım" tabı üçün istifadə olunur.
        """
        user = request.user
        date_str = request.query_params.get('date')

        try:
            evaluation_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except ValueError:
            return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)
        
        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(user, context=context)
        return Response(serializer.data)
        
    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        user = self.request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
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
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response({'error': 'evaluatee_id parametri tələb olunur.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        user = self.request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        try:
            end_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1) if date_str else timezone.now().date().replace(day=1)
        except ValueError:
            return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)

        summary = {
            'evaluatee_id': evaluatee.id,
            'evaluatee_name': evaluatee.get_full_name(),
            'averages': {}
        }
        
        periods = {'3 ay': 3, '6 ay': 6, '9 ay': 9, '1 il': 12}

        for label, months in periods.items():
            start_date = end_date - relativedelta(months=months) + relativedelta(days=1)
            
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