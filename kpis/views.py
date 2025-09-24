from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Prefetch

from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email
from accounts.models import User, Department # Department modeli import edildi
from tasks.models import Task
from tasks.serializers import TaskSerializer


class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    # ===========================================================================
    # YARDIMCI METOTLAR
    # ===========================================================================

    def get_direct_superior(self, user):
        """
        Verilen kullanıcının hiyerarşideki doğrudan (bir üst) amirini bulur.
        Bu fonksiyon, sıralı değerlendirme mantığının temelini oluşturur.
        """
        if not hasattr(user, 'department') or not user.department:
            return None

        if user.role == 'employee':
            # Çalışanın yöneticisini (manager) kendi departmanında arar
            return User.objects.filter(role='manager', department=user.department).first()
        
        elif user.role == 'manager':
            # Yöneticinin departman liderini (department_lead) arar
            # Department modelinden departmanın liderini buluruz
            try:
                # Departmanın 'lead' alanı, department_lead rolündeki kullanıcıyı işaret etmelidir
                return user.department.lead
            except (Department.DoesNotExist, AttributeError):
                return None
        
        elif user.role == 'department_lead':
            # Departman liderinin amiri 'top_management' rolündeki bir kullanıcıdır
            return User.objects.filter(role='top_management').first()
            
        # top_management ve diğer rollerin doğrudan bir amiri yoktur
        return None

    def get_user_subordinates(self, user):
        """
        Kullanıcının hiyerarşik olarak altındaki tüm çalışanları döndürür.
        """
        if user.role == 'admin':
            return User.objects.exclude(role__in=['admin', 'top_management'])
        if user.role == 'top_management':
            # top_management, kendisi ve admin hariç herkesi görür
            return User.objects.exclude(role__in=['admin', 'top_management'])
        if user.role == 'department_lead':
            # Departman lideri, kendi departmanındaki yönetici ve çalışanları görür
            return User.objects.filter(department=user.department, role__in=['manager', 'employee'])
        if user.role == 'manager':
            # Yönetici, kendi departmanındaki çalışanları görür
            return User.objects.filter(department=user.department, role='employee')
        
        # Diğer rollerin (örn: employee) astı yoktur
        return User.objects.none()

    # ===========================================================================
    # ANA VIEWSET METOTLARI
    # ===========================================================================

    def get_queryset(self):
        """
        Daha akıllı bir filtreleme yapar:
        - Kullanıcı kendiyle ilgili (değerlendiren veya değerlendirilen olduğu) tüm kayıtları görebilir.
        - Kullanıcı, astlarının TAMAMLANMIŞ değerlendirme sonuçlarını da görebilir.
        """
        user = self.request.user
        
        if user.role == 'admin':
            return KPIEvaluation.objects.all().select_related('task', 'evaluator', 'evaluatee')

        # 1. Kullanıcının doğrudan dahil olduğu değerlendirmeler
        my_direct_evaluations_q = Q(evaluator=user) | Q(evaluatee=user)

        # 2. Kullanıcının astlarının tamamlanmış (yani amir tarafından değerlendirilmiş) sonuçları
        subordinates = self.get_user_subordinates(user)
        if subordinates.exists():
            # Sadece amir tarafından değerlendirilmiş kayıtların ID'lerini alıyoruz
            completed_subordinate_eval_ids = KPIEvaluation.objects.filter(
                evaluatee__in=subordinates,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).values_list('task_id', flat=True)

            # Bu task_id'lere ait tüm değerlendirmeleri (hem self hem superior) alıyoruz
            completed_subordinate_evaluations_q = Q(task_id__in=completed_subordinate_eval_ids)
        else:
            completed_subordinate_evaluations_q = Q()

        query = my_direct_evaluations_q | completed_subordinate_evaluations_q
        
        return KPIEvaluation.objects.filter(query).distinct().select_related(
            'task', 'assignee', 'evaluator', 'evaluatee'
        )

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        # Kural 1: 'top_management' rolü değerlendirilemez.
        if evaluatee.role == 'top_management':
            raise ValidationError("Top management rolündeki kullanıcılar için KPI değerlendirmesi yapılamaz.")

        if evaluator == evaluatee:
            # === Öz Değerlendirme Mantığı ===
            if KPIEvaluation.objects.filter(task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION).exists():
                raise ValidationError("Bu görev için zaten öz değerlendirmenizi yaptınız.")
            
            instance = serializer.save(evaluator=evaluator, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION)
            
            try:
                # E-posta bildirimini sadece öz değerlendirme sonrası gönderiyoruz
                send_kpi_evaluation_request_email(instance)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Değerlendirme e-postası gönderilemedi: {str(e)}")

        else:
            # === Amir Değerlendirmesi Mantığı ===
            direct_superior = self.get_direct_superior(evaluatee)
            
            # Kural 2: Sadece doğrudan amir veya admin değerlendirebilir.
            if evaluator != direct_superior and evaluator.role != 'admin':
                raise PermissionDenied(f"Bu çalışanı ('{evaluatee.get_full_name()}') sadece doğrudan amiri ('{direct_superior.get_full_name() if direct_superior else 'Bulunamadı'}') değerlendirebilir.")

            # Kural 3: Amir değerlendirmesi için önce öz değerlendirme yapılmalıdır.
            if not KPIEvaluation.objects.filter(task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION).exists():
                raise ValidationError("Bu değerlendirmeyi yapmadan önce çalışanın öz değerlendirmesini tamamlaması gerekir.")

            # Kural 4: Bir görev için sadece bir amir değerlendirmesi olabilir.
            if KPIEvaluation.objects.filter(task=task, evaluatee=evaluatee, evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION).exists():
                raise ValidationError("Bu çalışan bu görev için zaten bir amir tarafından değerlendirilmiş.")

            serializer.save(evaluator=evaluator, evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION)
    
    # ===========================================================================
    # ÖZEL ENDPOINT'LER (ACTIONS)
    # ===========================================================================

    @action(detail=False, methods=['get'])
    def kpi_dashboard_tasks(self, request):
        """
        KPI paneli için görevleri listeler. Frontend bu endpoint'i kullanmalıdır.
        Tüm filtreleme ve yetki mantığı bu fonksiyonda toplanmıştır.
        """
        user = self.request.user
        
        user_tasks_q = Q(assignee=user, status='DONE')
        
        subordinates = self.get_user_subordinates(user)
        subordinate_tasks_q = Q(assignee__in=subordinates, status='DONE')
        
        # 'top_management' rolüne atanan görevler değerlendirme listesine dahil edilmez
        all_tasks_query = Task.objects.filter(user_tasks_q | subordinate_tasks_q) \
            .exclude(assignee__role='top_management') \
            .order_by('-created_at')

        # N+1 problemini önlemek ve ilgili tüm değerlendirmeleri tek seferde çekmek için prefetch
        tasks_with_evaluations = all_tasks_query.select_related(
            'assignee', 'created_by'
        ).prefetch_related(
            'evaluations', 'evaluations__evaluator'
        )

        final_tasks_for_frontend = []
        for task in tasks_with_evaluations:
            evaluations = list(task.evaluations.all())
            has_self_eval = any(e.evaluation_type == 'SELF' for e in evaluations)
            has_superior_eval = any(e.evaluation_type == 'SUPERIOR' for e in evaluations)
            
            # === Frontend'e gönderilecek görevleri belirleyen ana mantık ===
            
            # Durum 1: Görev, giriş yapan kullanıcıya aitse (kendi öz değerlendirmesi için)
            if task.assignee == user:
                final_tasks_for_frontend.append(task)
                continue

            # Durum 2: Görev, kullanıcının bir astına aitse
            if task.assignee in subordinates:
                direct_superior = self.get_direct_superior(task.assignee)
                
                # a) Sıralı Değerlendirme: Değerlendirme sırası bendeyse (doğrudan amiriysem)
                #    ve henüz amir değerlendirmesi yapılmamışsa, listeye ekle.
                if user == direct_superior and has_self_eval and not has_superior_eval:
                    final_tasks_for_frontend.append(task)
                
                # b) Görüntüleme: Değerlendirme zaten tamamlandıysa, tüm üstler sonucu
                #    görebilmesi için listeye ekle.
                elif has_superior_eval:
                    final_tasks_for_frontend.append(task)
                
                # c) İstisna: Admin her zaman tüm görevleri görür.
                elif user.role == 'admin':
                    final_tasks_for_frontend.append(task)

        serializer = TaskSerializer(final_tasks_for_frontend, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_evaluations(self, request):
        user = request.user
        
        # get_queryset artık doğru filtrelemeyi yaptığı için burası sade kalabilir
        given_evaluations = self.get_queryset().filter(evaluator=user)
        received_evaluations = self.get_queryset().filter(evaluatee=user)
        
        return Response({
            'given': KPIEvaluationSerializer(given_evaluations, many=True).data,
            'received': KPIEvaluationSerializer(received_evaluations, many=True).data
        })

    @action(detail=False, methods=['get'])
    def task_evaluations(self, request):
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id parametresi zorunludur'}, status=status.HTTP_400_BAD_REQUEST)
        
        # get_queryset yetkileri de kontrol ettiği için güvenlidir
        evaluations = self.get_queryset().filter(task_id=task_id)
        return Response(KPIEvaluationSerializer(evaluations, many=True).data)