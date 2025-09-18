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
        related_name='managed_department'
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}  "

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
    
    def get_superior(self):
        if self.role == "employee":
            if not self.department:
                return None
            return self.department.manager or self.department.lead

        elif self.role == "manager":
            if hasattr(self, 'managed_department'):
                return self.managed_department.lead
            return None

        elif self.role == "department_lead":
            return User.objects.filter(role="top_management").first()

        else:
            return None
        
    def get_assignable_users(self):
        """
        Returns a queryset of users to whom this user can assign tasks based on 
        role hierarchy and department rules.
        """
        # Admin/staff can assign to anyone active (except themselves).
        if self.is_staff or self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk)

        # Top management can assign tasks to all department leads.
        if self.role == "top_management":
            return User.objects.filter(role="department_lead", is_active=True)
        
        # A user must be in a department to assign tasks (unless they are top management).
        if not self.department:
            return User.objects.none()

        # Department leads can assign to managers and employees in their department.
        if self.role == "department_lead":
            if hasattr(self, 'led_department'):
                return User.objects.filter(
                    department=self.department,
                    role__in=["manager", "employee"],
                    is_active=True
                )

        # A manager can assign tasks only to employees in the department they officially manage.
        if self.role == "manager":
            if hasattr(self, 'managed_department') and self.managed_department:
                return User.objects.filter(
                    department=self.managed_department,
                    role="employee",
                    is_active=True
                )
        
        # Employees or other roles cannot assign tasks.
        return User.objects.none()
