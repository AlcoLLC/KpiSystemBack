from django.db import models
from django.contrib.auth.models import User


class Department(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Employee(models.Model):
    ROLE_CHOICES = [
        ("employee", "Employee"),
        ("manager", "Manager"),
        ("department_lead", "Department Lead"),
        ("top_manager", "Top Manager"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="employees")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class KPIEvaluation(models.Model):
    evaluator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="given_evaluations")
    evaluatee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="received_evaluations")
    score = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("evaluator", "evaluatee")

    def __str__(self):
        return f"{self.evaluator} -> {self.evaluatee}: {self.score}"
