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
        "top_management_score", 
        "final_score",
        "created_at",
        "updated_by",
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
        "previous_score",
        "updated_by",
        "history",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("task", "evaluator", "evaluatee", "updated_by")

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
                "top_management_score", 
                "final_score",
                "previous_score",
            )
        }),
        ("Dəyişiklik Tarixçəsi və Əlavə", {
            "fields": (
                "comment",
                "attachment",
                "updated_by",
                "history",
                "created_at",
                "updated_at",
            )
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['self_score'].widget.attrs['disabled'] = True
        form.base_fields['superior_score'].widget.attrs['disabled'] = True
        if 'top_management_score' in form.base_fields: 
            form.base_fields['top_management_score'].widget.attrs['disabled'] = True

        if obj:
            if obj.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
                form.base_fields['self_score'].widget.attrs.pop('disabled', None)
                form.base_fields['self_score'].help_text = "İşçinin öz dəyərləndirməsidir (1-10 arası)."

            elif obj.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                form.base_fields['superior_score'].widget.attrs.pop('disabled', None)
                form.base_fields['superior_score'].help_text = "Üst rəhbərin dəyərləndirməsidir (1-100 arası)."

            elif obj.evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
                if 'top_management_score' in form.base_fields:
                    form.base_fields['top_management_score'].widget.attrs.pop('disabled', None)
                    form.base_fields['top_management_score'].help_text = "Yuxarı İdarəetmənin dəyərləndirməsidir (1-100 arası)."

        return form