from django.contrib import admin
from .models import Department, Employee, KPIEvaluation


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "department", "role")
    list_filter = ("role", "department")


@admin.register(KPIEvaluation)
class KPIEvaluationAdmin(admin.ModelAdmin):
    list_display = ("id", "evaluator", "evaluatee", "score", "created_at")
    list_filter = ("score", "created_at")
