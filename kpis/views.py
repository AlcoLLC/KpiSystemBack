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

        else:
            if evaluatee.role == "employee" and evaluator.role not in ["manager", "department_lead"]:
                raise PermissionDenied("Yalnız Manager və ya Department Lead işçini dəyərləndirə bilər.")
            elif evaluatee.role == "manager" and evaluator.role != "department_lead":
                raise PermissionDenied("Yalnız Department Lead meneceri dəyərləndirə bilər.")
            # ... diğer roller için kontroller ...
            elif evaluator != evaluatee.get_superior():
                 raise PermissionDenied("Yalnız bu işçinin birbaşa rəhbəri dəyərləndirmə edə bilər.")

            if not KPIEvaluation.objects.filter(
                task=task,
                evaluatee=evaluatee,
                evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
            ).exists():
                raise PermissionDenied("Bu dəyərləndirməni etməzdən əvvəl işçi öz dəyərləndirməsini tamamlamalıdır.")

            if KPIEvaluation.objects.filter(
                task=task, 
                evaluator=evaluator, 
                evaluatee=evaluatee, 
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            ).exists():
                raise ValidationError("Bu işçini bu tapşırıq üçün artıq dəyərləndirmisiniz.")

            serializer.save(
                evaluator=evaluator,
                evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
            )