# models.py
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
    
    # Yeni alanlar - Skorları ayrı tutmaq üçün
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
    
    # Əsas skor - üst rəhbərin verdiyi skor sayılır
    final_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Son skor - üst rəhbərin verdiyi skor"
    )
    
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Evaluation type
    evaluation_type = models.CharField(
        max_length=10,
        choices=EvaluationType.choices,
        default=EvaluationType.SUPERIOR_EVALUATION,
    )

    class Meta:
        unique_together = ("task", "evaluator", "evaluatee", "evaluation_type")

    def save(self, *args, **kwargs):
        # Final score hesaplama
        if self.evaluation_type == self.EvaluationType.SUPERIOR_EVALUATION and self.superior_score:
            self.final_score = self.superior_score
        super().save(*args, **kwargs)

    def __str__(self):
        return f"KPI {self.task.title}: {self.evaluator} -> {self.evaluatee} - [{self.get_evaluation_type_display()}]"

