from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

class UserEvaluation(models.Model):
    class EvaluationType(models.TextChoices):
        SUPERIOR_EVALUATION = 'SUPERIOR', 'Üst Rəhbər Dəyərləndirməsi'
        TOP_MANAGEMENT_EVALUATION = 'TOP_MANAGEMENT', 'Yuxarı İdarəetmə Dəyərləndirməsi'

    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_user_evaluations",
        help_text="Dəyərləndirməni edən şəxs"
    )
    evaluatee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_user_evaluations",
        help_text="Dəyərləndirilən işçi"
    )
    
    evaluation_type = models.CharField(
        max_length=20, 
        choices=EvaluationType.choices, 
        help_text="Dəyərləndirmənin növü (Üst Rəhbər və ya Top Management)"
    )

    score = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Aylıq performans skoru (1-10 arası)"
    )
    
    comment = models.TextField(
        blank=True,
        null=True,
        help_text="Dəyərləndirmə ilə bağlı əlavə qeydlər"
    )
    
    evaluation_date = models.DateField(
        help_text="Dəyərləndirmənin aid olduğu ay və il (örn: 2025-10-01)"
    )
    
    previous_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Dəyişiklik edildikdə əvvəlki skor"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_user_evaluations",
        help_text="Dəyərləndirməni son redaktə edən şəxs"
    )
    history = models.JSONField(
        default=list,
        blank=True,
        help_text="Dəyərləndirmə dəyişikliklərinin tarixçəsi"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('evaluatee', 'evaluation_date', 'evaluation_type') 
        ordering = ['-evaluation_date', 'evaluatee']
        verbose_name = "KPI Evaluation"
        verbose_name_plural = "KPI Evaluations"
        
    def __str__(self):
        return f"{self.get_evaluation_type_display()} for {self.evaluatee.get_full_name()} on {self.evaluation_date.strftime('%Y-%m')}"