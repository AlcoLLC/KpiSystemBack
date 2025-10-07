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
    İstifadəçi performans dəyərləndirmələrini rol və departamentə əsaslanan
    icazələrlə idarə edir.
    """
    queryset = UserEvaluation.objects.select_related('evaluator', 'evaluatee', 'updated_by').all()
    serializer_class = UserEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Dəyərləndirmələri ciddi iyerarxik və departament məntiqi ilə filtrləyir.
        - **Admin/Staff:** Hər şeyi görür.
        - **Top Management:** Özündən aşağı bütün rolları departament məhdudiyyəti olmadan görür.
        - **Digər Rollar (Lead, Manager):** Yalnız öz dəyərləndirmələrini və öz departamentləri daxilindəki astlarına aid olanları görür.
        - **Employee:** Yalnız öz dəyərləndirmələrini görür.
        """
        user = self.request.user

        if user.is_staff or user.role == 'admin':
            return self.queryset.order_by('-evaluation_date')

        # Hər bir istifadəçi öz dəyərləndirməsini mütləq görə bilər.
        q_objects = Q(evaluatee=user)

        # Rollara görə tabeliyindəki işçiləri görmə icazələri əlavə edilir.
        if user.role == 'top_management':
            # Top Management bütün departamentlərdəki department_lead, manager və employee-ləri görə bilir.
            q_objects |= Q(evaluatee__role__in=['department_lead', 'manager', 'employee'])
        
        elif user.role == 'department_lead' and user.department:
            # Department Lead-lər yalnız öz departamentləri daxilindəki manager və employee-ləri görür.
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role__in=['manager', 'employee']
            )
        
        elif user.role == 'manager' and user.department:
            # Manager-lər yalnız öz departamentləri daxilindəki employee-ləri görür.
            q_objects |= Q(
                evaluatee__department=user.department,
                evaluatee__role='employee'
            )
        
        # 'Employee' rolu üçün yuxarıdakı şərtlərin heç biri ödənmir,
        # buna görə yalnız ilkin `Q(evaluatee=user)` filtri aktiv qalır.

        return self.queryset.filter(q_objects).distinct().order_by('-evaluation_date')

    def perform_create(self, serializer):
        """
        Yeni bir dəyərləndirməni yadda saxlayır və cari istifadəçini qiymətləndirən kimi təyin edir.
        Yaratma icazəsi serialayzerin validasiya məntiqində yoxlanılır.
        """
        evaluatee = serializer.validated_data['evaluatee']
        serializer.save(evaluator=self.request.user, evaluatee=evaluatee)

    def partial_update(self, request, *args, **kwargs):
        """
        Dəyərləndirməni yalnız Admin və ya qiymətləndirilənin
        mövcud birbaşa rəhbərinin redaktə etməsinə icazə verir.
        """
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
        Sorğu göndərən istifadəçinin dəyərləndirmə səlahiyyəti olan işçiləri siyahılayır.
        - **Employee:** Heç kimi dəyərləndirə bilməz (boş siyahı qayıdır).
        - **Manager/Lead:** Yalnız öz departamentindəki astlarını dəyərləndirə bilər.
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
        
        # İlkin olaraq boş bir nəticə queryset-i təyin edilir.
        subordinates = User.objects.none()

        if evaluator.is_staff or evaluator.role == 'admin':
            # Adminlər top management xaricində hər kəsi dəyərləndirə bilər.
            subordinates = User.objects.filter(is_active=True).exclude(Q(id=evaluator.id) | Q(role='top_management'))
        
        elif evaluator.role == 'top_management':
            # Top management bütün departamentlərdəki lead, manager və employee-ləri dəyərləndirə bilər.
            subordinates = User.objects.filter(is_active=True, role__in=['department_lead', 'manager', 'employee']).exclude(id=evaluator.id)

        # Digər rolların kimisə dəyərləndirməsi üçün mütləq departamenti olmalıdır.
        elif evaluator.department:
            # Baza queryset: eyni departamentdəki aktiv istifadəçilər (istifadəçinin özü xaric).
            base_department_qs = User.objects.filter(
                is_active=True, 
                department=evaluator.department
            ).exclude(id=evaluator.id)

            if evaluator.role == 'department_lead':
                # Lead-lər öz departamentindəki manager və employee-ləri dəyərləndirir.
                subordinates = base_department_qs.filter(role__in=['manager', 'employee'])
            
            elif evaluator.role == 'manager':
                # Manager-lər öz departamentindəki employee-ləri dəyərləndirir.
                subordinates = base_department_qs.filter(role='employee')
            
            # 'Employee' rolu yuxarıdakı şərtlərin heç birinə uyğun gəlmədiyi üçün `subordinates` boş qalır.
        
        # Frontend-dən gələn əlavə departament filtri (əsasən Admin və Top Management üçün).
        if department_id:
            try:
                subordinates = subordinates.filter(department_id=int(department_id))
            except (ValueError, TypeError):
                return Response({'error': 'Departament ID düzgün deyil.'}, status=status.HTTP_400_BAD_REQUEST)

        context = {'request': request, 'evaluation_date': evaluation_date}
        serializer = UserForEvaluationSerializer(subordinates, many=True, context=context)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='monthly-scores')
    def monthly_scores(self, request):
        """
        Bir işçinin aylıq qiymətlərini qaytarır.
        Seçilmiş tarixə qədər olan nəticələri göstərmək üçün 'date' parametri ilə filtrlənə bilər.
        Params: ?evaluatee_id=<user_id>&date=<YYYY-MM>
        """
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response(
                {'error': 'evaluatee_id parametri tələb olunur.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        # İcazə yoxlaması
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        # Baza queryset
        scores = UserEvaluation.objects.filter(evaluatee=evaluatee)

        # Tarix parametri varsa, nəticələri filtrlə
        if date_str:
            try:
                # Seçilmiş ayın sonuna qədər olan bütün nəticələri al.
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
        """
        Bir işçinin performans ortalamalarını hesablayır.
        Həmin tarixə qədər olan dövrlər üçün ortalamaları hesablamaq məqsədilə
        'date' parametri qəbul edir.
        """
        evaluatee_id = request.query_params.get('evaluatee_id')
        date_str = request.query_params.get('date')

        if not evaluatee_id:
            return Response(
                {'error': 'evaluatee_id parametri tələb olunur.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
        except User.DoesNotExist:
            return Response({'error': 'İşçi tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)

        # İcazə yoxlaması
        user = request.user
        if not (user.is_staff or user.role == 'admin' or user == evaluatee or user in evaluatee.get_all_superiors()):
            raise PermissionDenied("Bu işçinin məlumatlarını görməyə icazəniz yoxdur.")

        # Hesablamalar üçün son tarixi müəyyən et.
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
                evaluation_date__lte=end_date
            ).aggregate(
                average_score=Avg('score')
            )
            
            average = avg_data['average_score']
            summary['averages'][label] = round(average, 2) if average else None

        return Response(summary)