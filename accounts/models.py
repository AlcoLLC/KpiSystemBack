from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
import itertools

class Department(models.Model):
    name = models.CharField(max_length=255)
    manager = models.OneToOneField(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="managed_department"
    )
    lead = models.ForeignKey(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="led_departments"
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
    slug = models.SlugField(unique=True, max_length=255, blank=True, null=True)

    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.first_name}-{self.last_name}") or slugify(self.username)
            slug = base_slug

            for i in itertools.count(1):
                if not User.objects.filter(slug=slug).exists():
                    break
                slug = f'{base_slug}-{i}'
            self.slug = slug
        super().save(*args, **kwargs)


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

    def get_direct_superior(self):
        """
        Finds the user's direct superior based on the defined hierarchy.
        - Employee -> Manager (if no manager -> Dept Lead) (if no lead -> Top Management)
        - Manager -> Dept Lead (if no lead -> Top Management)`
        - Dept Lead -> Top Management
        """
        if self.role in ["top_management", "admin"]:
            return None

        # Department-level hierarchy check
        if self.department:
            # For an Employee, first check for a Manager in the same department
            if self.role == "employee":
                manager = User.objects.filter(
                    department=self.department, role="manager", is_active=True
                ).first()
                if manager:
                    return manager
            
            # For an Employee (if no manager) or a Manager, check for a Department Lead
            if self.role in ["employee", "manager"]:
                lead = User.objects.filter(
                    department=self.department, role="department_lead", is_active=True
                ).first()
                if lead:
                    return lead

        # Fallback for all roles, or if no department-level superior is found
        return User.objects.filter(role="top_management", is_active=True).first()
    
    # accounts/models.py -> User class

    def get_all_superiors(self):
        """
        Returns a list of all superiors in the hierarchy for this user.
        e.g., [manager, department_lead, top_management]
        """
        superiors = []
        current_superior = self.get_direct_superior()
        # Add a safety limit to prevent infinite loops in case of misconfiguration
        limit = 10 
        count = 0
        while current_superior and count < limit:
            superiors.append(current_superior)
            current_superior = current_superior.get_direct_superior()
            count += 1
        return superiors