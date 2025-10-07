from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
import datetime

class UserEvaluation(models.Model):
    """
    Represents a monthly performance evaluation of a user by their superior.
    """
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_user_evaluations",
        help_text="Dəyərləndirməni edən şəxs (rəhbər)"
    )
    evaluatee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_user_evaluations",
        help_text="Dəyərləndirilən işçi"
    )
    
    score = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Aylıq performans skoru (1-100 arası)"
    )
    
    comment = models.TextField(
        blank=True,
        null=True,
        help_text="Dəyərləndirmə ilə bağlı əlavə qeydlər"
    )
    
    evaluation_date = models.DateField(
        help_text="Dəyərləndirmənin aid olduğu ay və il (örn: 2025-10-01)"
    )
    
    # --- Değişiklik Takibi ---
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
        # Bir işçi üçün bir ayda yalnız bir dəyərləndirmə ola bilər
        unique_together = ('evaluatee', 'evaluation_date')
        ordering = ['-evaluation_date', 'evaluatee']

    def __str__(self):
        return f"Evaluation for {self.evaluatee.get_full_name()} on {self.evaluation_date.strftime('%Y-%m')}"