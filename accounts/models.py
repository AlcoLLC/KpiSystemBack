from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("top_management", "Top Management"),
        ("department_lead", "Department Lead"),
        ("manager", "Manager"),
        ("employee", "Employee"),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Department(models.Model):
    name = models.CharField(max_length=255)
    manager = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_department"
    )
    lead = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="led_department"
    )

    def __str__(self):
        return self.name
