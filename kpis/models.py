from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from tasks.models import Task

class KPIEvaluation(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="evaluations")
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="given_kpis"
    )
    evaluatee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_kpis"
    )
    score = models.PositiveIntegerField()
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("task", "evaluator", "evaluatee")

    def __str__(self):
        return f"KPI {self.task.title}: {self.evaluator} -> {self.evaluatee} ({self.score})"