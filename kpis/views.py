from rest_framework import viewsets, permissions
from .models import Department, Employee, KPIEvaluation
from .serializers import DepartmentSerializer, EmployeeSerializer, KPIEvaluationSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]


class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    # permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        evaluator = Employee.objects.get(user=self.request.user)
        serializer.save(evaluator=evaluator)
