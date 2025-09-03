from django.contrib import admin
from .models import KPIEvaluation

@admin.register(KPIEvaluation)
class KPIEvaluationAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "evaluator", "evaluatee", "score", "created_at")
    list_filter = ("score", "created_at")
