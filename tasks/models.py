from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class Task(models.Model):
    STATUS_CHOICES = [
        ("PENDING", _("Gözləmədə")),
        ("TODO", _("Təsdiqlənib")),
        ("IN_PROGRESS", _("Davam edir")),
        ("DONE", _("Tamamlanıb")),
        ("CANCELLED", _("Ləğv edilib")),
    ]

    PRIORITY_CHOICES = [
        ("CRITICAL", _("Çox vacib")),
        ("HIGH", _("Yüksək")),
        ("MEDIUM", _("Orta")),
        ("LOW", _("Aşağı")),
    ]


    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_tasks"
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    # estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    approved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tamamlanma tarixi")
    
    def save(self, *args, **kwargs):
        if self.status == 'DONE' and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} -> {self.assignee.username}"