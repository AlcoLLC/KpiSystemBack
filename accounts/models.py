from django.db import models
from django.contrib.auth.models import AbstractUser

class Department(models.Model):
    name = models.CharField(max_length=255)
    manager = models.OneToOneField(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="managed_department"
    )
    lead = models.OneToOneField(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="led_department"
    )

    def __str__(self):
        return self.name

class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("top_management", "Top Management"),
        ("department_lead", "Department Lead"),
        ("manager", "Manager"),
        ("employee", "Employee"),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    department = models.ForeignKey(
        Department, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='employees'
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def assigner_role(self):
        """Determines the superior role based on the user's role."""
        role_hierarchy = {
            "employee": "Manager or Department Lead",
            "manager": "Department Lead",
            "department_lead": "Top Management",
            "top_management": "N/A", 
            "admin": "N/A",
        }
        return role_hierarchy.get(self.role, "Unknown")