# evaluations/views.py

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Avg, Q
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .models import UserEvaluation
from .serializers import UserEvaluationSerializer, UserForEvaluationSerializer, MonthlyScoreSerializer
from accounts.models import User

# Role hierarchy for easier comparison
ROLE_HIERARCHY = {
    'employee': 1,
    'manager': 2,
    'department_lead': 3,
    'top_management': 4,
    'admin': 5, # Admin has the highest level
}


class UserEvaluationViewSet(viewsets.ModelViewSet):
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filters evaluations based on a strict hierarchical and departmental logic.
        - Admins/Staff see everything.
        - Users see their own evaluations.
        - Superiors see evaluations of their subordinates within their department.
        """
        user = self.request.user

        if user.is_staff or user.role == 'admin':
            return self.queryset.order_by('-evaluation_date')

        # Base query for the user's own evaluations
        q_objects = Q(evaluatee=user)

        # Add subordinates' evaluations based on role and department
        if user.role == 'top_management':
            # Top Management sees all leads, managers, and employees
            q_objects |= Q(evaluatee__role__in=['department_lead', 'manager', 'employee'])
        
        elif user.role == 'department_lead' and user.department:
            # Department Leads see managers and employees in their department
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role__in=['manager', 'employee']
            )
        
        elif user.role == 'manager' and user.department:
            # Managers see employees in their department
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role='employee'
            )
        
        return self.queryset.filter(q_objects).distinct().order_by('-evaluation_date')

    def perform_create(self, serializer):
        """
        The validation for creation is handled in the serializer's validate method.
        This simply sets the evaluator.
        """
        evaluatee = serializer.validated_data['evaluatee']
        
        # The serializer already validates if the request.user can evaluate the evaluatee.
        # So we can safely save here.
        serializer.save(evaluator=self.request.user, evaluatee=evaluatee)

    def partial_update(self, request, *args, **kwargs):
        """
        Allows editing only by an admin or the evaluatee's CURRENT direct superior.
        """
        instance = self.get_object()
        user = request.user
        evaluatee = instance.evaluatee
        
        # Check for permission
        is_admin = user.is_staff or user.role == 'admin'
        is_direct_superior = evaluatee.get_direct_superior() == user
        
        if not (is_admin or is_direct_superior):
            raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə yalnız birbaşa rəhbər və ya Admin icazəlidir.")

        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='evaluable-users')
    def evaluable_users(self, request):
        """
        Lists users that the requesting user has the authority to evaluate based on
        the defined hierarchy.
        """
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
        
        # Base queryset for all potential subordinates
        subordinates_qs = User.objects.filter(is_active=True).exclude(id=evaluator.id)

        # Apply hierarchical filtering
        if evaluator.is_staff or evaluator.role == 'admin':
            # Admins can evaluate anyone except top management
            subordinates = subordinates_qs.exclude(role='top_management')
        elif evaluator.role == 'top_management':
            # Top management evaluates leads, managers, and employees
            subordinates = subordinates_qs.filter(role__in=['department_lead', 'manager', 'employee'])
        elif evaluator.role == 'department_lead':
            # Leads evaluate managers and employees in their department
            subordinates = subordinates_qs.filter(department=evaluator.department, role__in=['manager', 'employee'])
        elif evaluator.role == 'manager':
            # Managers evaluate employees in their department
            subordinates = subordinates_qs.filter(department=evaluator.department, role='employee')
        else: # Employees cannot evaluate anyone
            subordinates = User.objects.none()

        # Apply optional department filter from query params
        if department_id:
            try:
                subordinates = subordinates.filter(department_id=int(department_id))
            except (ValueError, TypeError):
                return Response({'error': 'Departament ID düzgün deyil.'}, status=status.HTTP_400_BAD_REQUEST)

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(subordinates, many=True, context=context)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='performance-summary')
    def performance_summary(self, request):
        """
        Calculates performance summary for an employee. Now accepts an optional 'date'
        query parameter to calculate averages for periods ending on that date.
        """
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date') # Expects 'YYYY-MM'

        if not evaluatee_id:
            return Response(
                {'error': 'evaluatee_id parametri tələb olunur.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        # Permission Check (Same as before, relies on get_all_superiors)
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        # Determine the end date for calculations
        try:
            if date_str:
                end_date = datetime.strptime(date_str, '%Y-%m').date().replace(day=1)
            else:
                end_date = timezone.now().date().replace(day=1)
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
                evaluation_date__lte=end_date # Ensure we don't include future data
            ).aggregate(
                average_score=Avg('score')
            )
            
            average = avg_data['average_score']
            summary['averages'][label] = round(average, 2) if average else None

        return Response(summary)

    # monthly_scores action remains the same.
    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        """
        Bir işçinin aylıq qiymətlərini qaytarır.
        İndi seçilmiş tarixə qədər olan nəticələri filtrləmək üçün 
        'date' query parametri də qəbul edir.
        Query Params: ?evaluatee_id=<user_id>&date=<YYYY-MM>
        """
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date') # <-- ADDED: Get the date parameter

        if not evaluatee_id:
            return Response(
                {'error': 'evaluatee_id parametri tələb olunur.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        # Permission check remains the same
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        # Start with the base queryset
        scores = UserEvaluation.objects.filter(evaluatee=evaluatee)

        # <-- ADDED: Filter by date if the parameter is provided -->
        if date_str:
            try:
                # We want all scores up to the end of the selected month
                end_date = datetime.strptime(date_str, '%Y-%m').date()
                end_date = end_date + relativedelta(months=1) - relativedelta(days=1)
                scores = scores.filter(evaluation_date__lte=end_date)
            except ValueError:
                return Response({'error': 'Tarix formatı yanlışdır. Format YYYY-MM olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)
        # <-- END OF ADDED LOGIC -->

        # Order and serialize the (potentially filtered) results
        scores = scores.order_by('-evaluation_date')
        serializer = MonthlyScoreSerializer(scores, many=True)
        return Response(serializer.data)