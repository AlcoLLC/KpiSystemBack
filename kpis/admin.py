from django.contrib import admin
from .models import KPIEvaluation


@admin.register(KPIEvaluation)
class KPIEvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "evaluator",
        "evaluatee",
        "evaluation_type",
        "self_score",
        "superior_score",
        "final_score",
        "created_at",
    )
    list_filter = (
        "evaluation_type",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "task__title",
        "evaluator__username",
        "evaluatee__username",
        "comment",
    )
    readonly_fields = (
        "final_score",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("task", "evaluator", "evaluatee")

    fieldsets = (
        (None, {
            "fields": (
                "task",
                "evaluator",
                "evaluatee",
                "evaluation_type",
            )
        }),
        ("Scores", {
            "fields": (
                "self_score",
                "superior_score",
                "final_score",
            )
        }),
        ("Additional Info", {
            "fields": (
                "comment",
                "created_at",
                "updated_at",
            )
        }),
    )
