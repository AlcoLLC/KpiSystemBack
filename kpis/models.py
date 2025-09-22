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
    
    score = models.PositiveIntegerField(null=True, blank=True)
    
    self_evaluation_score = models.PositiveIntegerField(null=True, blank=True)
    
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    evaluation_type = models.CharField(
        max_length=10,
        choices=EvaluationType.choices,
        default=EvaluationType.SELF_EVALUATION,
    )
    
    is_superior_evaluated = models.BooleanField(default=False)

    class Meta:
        unique_together = ("task", "evaluatee")

    def __str__(self):
        return f"KPI {self.task.title}: {self.evaluatee} - Self: {self.self_evaluation_score}/10, Superior: {self.score}/100"

    def get_final_score(self):
        """Final score olarak üst rolun verdiği değeri döndür"""
        return self.score if self.is_superior_evaluated else None

    def save(self, *args, **kwargs):
        if self.evaluation_type == self.EvaluationType.SELF_EVALUATION:
            if hasattr(self, '_temp_score'):
                self.self_evaluation_score = self._temp_score
                self.score = None  # İlk aşamada score null kalır
        elif self.evaluation_type == self.EvaluationType.SUPERIOR_EVALUATION:
            self.is_superior_evaluated = True
            
        super().save(*args, **kwargs)
