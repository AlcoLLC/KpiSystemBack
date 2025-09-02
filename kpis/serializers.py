from rest_framework import serializers
from .models import Department, Employee, KPIEvaluation


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class EmployeeSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()

    class Meta:
        model = Employee
        fields = "__all__"


class KPIEvaluationSerializer(serializers.ModelSerializer):
    evaluator = EmployeeSerializer(read_only=True)
    evaluatee = EmployeeSerializer(read_only=True)
    evaluator_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), write_only=True, source="evaluator"
    )
    evaluatee_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), write_only=True, source="evaluatee"
    )

    class Meta:
        model = KPIEvaluation
        fields = [
            "id", "evaluator", "evaluatee",
            "evaluator_id", "evaluatee_id",
            "score", "created_at"
        ]
