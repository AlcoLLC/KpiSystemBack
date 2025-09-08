from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver

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

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    email = models.EmailField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def role(self):
        return self.user.get_role_display()

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
        return role_hierarchy.get(self.user.role, "Unknown")

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()