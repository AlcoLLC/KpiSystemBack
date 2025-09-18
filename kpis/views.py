from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        # --- Öz-Dəyərləndirmə (Self-Evaluation) Hissəsi ---
        # Bu blokda heç bir dəyişiklik edilməyib.
        if evaluator == evaluatee:
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise ValidationError("Bu tapşırıq üçün artıq öz dəyərləndirmənizi etmisiniz.")
            
            instance = serializer.save(
                evaluator=evaluator, 
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            )
            send_kpi_evaluation_request_email(instance)

        # --- Rəhbər Dəyərləndirməsi (Superior Evaluation) Hissəsi ---
        # Bütün məntiq burada yenidən qurulub.
        else:
            # 1. Rol iyerarxiyasını aydın şəkildə müəyyən edirik.
            # Rəqəmlər rolun səviyyəsini göstərir: rəqəm nə qədər böyükdürsə, rol o qədər yüksəkdir.
            ROLE_HIERARCHY = {
                "employee": 1,
                "manager": 2,
                "department_lead": 3,
                "top_management": 4,
                "admin": 5
            }

            evaluator_level = ROLE_HIERARCHY.get(evaluator.role, 0)
            evaluatee_level = ROLE_HIERARCHY.get(evaluatee.role, 0)

            # 2. Dəyərləndirənin səviyyəsinin dəyərləndirilənin səviyyəsindən yüksək olub-olmadığını yoxlayırıq.
            # Bu, bütün iyerarxiya qaydalarını (admin > top_management, manager > employee və s.) əhatə edir.
            if evaluator_level <= evaluatee_level:
                raise PermissionDenied("Yalnız özünüzdən aşağı rolda olan işçiləri dəyərləndirə bilərsiniz.")

            # 3. İşçinin öz-dəyərləndirməni tamamlayıb-tamamlamadığını yoxlayırıq. (əvvəlki məntiq saxlanılır)
            if not KPIEvaluation.objects.filter(
                task=task,
                evaluatee=evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise PermissionDenied("Bu dəyərləndirməni etməzdən əvvəl işçi öz dəyərləndirməsini tamamlamalıdır.")

            # 4. Rəhbərin bu tapşırıq üçün artıq dəyərləndirmə edib-etmədiyini yoxlayırıq. (əvvəlki məntiq saxlanılır)
            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu işçini bu tapşırıq üçün artıq dəyərləndirmisiniz.")

            # 5. Bütün yoxlamalar uğurlu olarsa, dəyərləndirməni yaddaşa veririk.
            serializer.save(
                evaluator=evaluator,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            )