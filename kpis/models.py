from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
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
    
    # Rəhbərin verdiyi bal (100-lük sistem)
    score = models.PositiveIntegerField(
        blank=True, 
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    
    # İşçinin özünə verdiyi bal (10-luq sistem)
    self_score = models.PositiveIntegerField(
        blank=True, 
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )

    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    evaluation_type = models.CharField(
        max_length=10,
        choices=EvaluationType.choices,
        default=EvaluationType.SUPERIOR_EVALUATION,
    )

    class Meta:
        unique_together = ("task", "evaluator", "evaluatee", "evaluation_type")

    def __str__(self):
        display_score = self.score if self.evaluation_type == self.EvaluationType.SUPERIOR_EVALUATION else self.self_score
        return f"KPI {self.task.title}: {self.evaluator} -> {self.evaluatee} ({display_score}) - [{self.get_evaluation_type_display()}]"