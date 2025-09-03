from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        evaluator = self.request.user
        evaluatee = serializer.validated_data["evaluatee"]
        task = serializer.validated_data["task"]

        if evaluatee.role == "employee":
            if evaluator.role != "manager" and evaluator.role != "department_lead":
                raise PermissionDenied("Only Manager or Department Lead can evaluate Employee.")
        elif evaluatee.role == "manager":
            if evaluator.role != "department_lead":
                raise PermissionDenied("Only Department Lead can evaluate Manager.")
        elif evaluatee.role == "department_lead":
            if evaluator.role != "top_management":
                raise PermissionDenied("Only Top Management can evaluate Department Lead.")
        elif evaluatee.role == "top_management":
            raise PermissionDenied("Top Management cannot be evaluated.")

        serializer.save(evaluator=evaluator)
