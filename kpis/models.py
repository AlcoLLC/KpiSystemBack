from django.db import models
from django.conf import settings
from tasks.models import Task

class KPIEvaluation(models.Model):
    class EvaluationType(models.TextChoices):
        SELF_EVALUATION = 'SELF', 'Öz Değerlendirme'
        SUPERIOR_EVALUATION = 'SUPERIOR', 'Üst Değerlendirmesi'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="evaluations")
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="given_kpis"
    )
    evaluatee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_kpis"
    )
    
    self_score = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="İşçinin özünə verdiği skor (1-10 arası)"
    )
    superior_score = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Üst rəhbərin verdiyi skor (1-100 arası)"
    )
    previous_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Dəyişiklik edildikdə əvvəlki skor"
    )
    
    final_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Son skor - üst rəhbərin verdiyi skor"
    )
    
    comment = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='kpi_attachments/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    evaluation_type = models.CharField(
        max_length=10,
        choices=EvaluationType.choices,
        default=EvaluationType.SUPERIOR_EVALUATION,
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_kpis",
        help_text="Dəyərləndirməni son redaktə edən şəxs"
    )
    history = models.JSONField(
        default=list,
        blank=True,
        help_text="Dəyərləndirmə dəyişikliklərinin tarixçəsi"
    )

    class Meta:
        unique_together = ("task", "evaluator", "evaluatee", "evaluation_type")

    def save(self, *args, **kwargs):
        if self.evaluation_type == self.EvaluationType.SUPERIOR_EVALUATION and self.superior_score is not None:
            self.final_score = self.superior_score
        super().save(*args, **kwargs)

    def __str__(self):
        return f"KPI {self.task.title}: {self.evaluator} -> {self.evaluatee} - [{self.get_evaluation_type_display()}]"

