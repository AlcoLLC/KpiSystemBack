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
        related_name="managed_department",
        limit_choices_to={'role': 'manager'}

    )
    lead = models.ManyToManyField(
        'User', 
        blank=True, 
        related_name="led_departments",
        limit_choices_to=models.Q(role='top_management') | models.Q(role='department_lead')
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
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk)

        if self.role == "top_management":
            return User.objects.filter(role="department_lead", is_active=True)
        
        if not self.department:
            return User.objects.none()

        if self.role == "department_lead":
            if hasattr(self, 'led_departments'):
                return User.objects.filter(
                    department=self.department,
                    role__in=["manager", "employee"],
                    is_active=True
                )
            
        if self.role == "manager":
            if hasattr(self, 'managed_department') and self.managed_department:
                return User.objects.filter(
                    department=self.managed_department,
                    role="employee",
                    is_active=True
                )
        
        return User.objects.none()

    def get_direct_superior(self):
        if self.role in ["top_management", "admin"]:
            return None

        if self.department:
            if self.role == "employee":
                manager = User.objects.filter(
                    department=self.department, role="manager", is_active=True
                ).first()
                if manager:
                    return manager
            
            if self.role in ["employee", "manager"]:
                lead = User.objects.filter(
                    department=self.department, role="department_lead", is_active=True
                ).first()
                if lead:
                    return lead

        return User.objects.filter(role="top_management", is_active=True).first()
    

    def get_all_superiors(self):
        superiors = []
        current_superior = self.get_direct_superior()
        limit = 10 
        count = 0
        while current_superior and count < limit:
            superiors.append(current_superior)
            current_superior = current_superior.get_direct_superior()
            count += 1
        return superiors
    

    def get_kpi_evaluator(self):
        if self.role in ["admin", "top_management"] or not self.department:
            return None

        if self.role == 'employee':
            manager = User.objects.filter(department=self.department, role='manager', is_active=True).first()
            if manager:
                return manager
        
        if self.role in ['employee', 'manager']:
            department_lead = User.objects.filter(department=self.department, role='department_lead', is_active=True).first()
            if department_lead:
                return department_lead

        if self.role in ['employee', 'manager', 'department_lead']:
            top_management = User.objects.filter(department=self.department, role='top_management', is_active=True).first()
            if top_management:
                return top_management
        
        return None

    def get_kpi_subordinates(self):
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(Q(id=self.id) | Q(role='top_management'))

        if not self.department:
            return User.objects.none()

        if self.role == 'top_management':
            return User.objects.filter(department=self.department, role__in=['department_lead', 'manager', 'employee'], is_active=True)
        elif self.role == 'department_lead':
            return User.objects.filter(department=self.department, role__in=['manager', 'employee'], is_active=True)
        elif self.role == 'manager':
            return User.objects.filter(department=self.department, role='employee', is_active=True)
        
        return User.objects.none()

    def get_kpi_superiors(self):
        superiors = []
        current_superior = self.get_kpi_evaluator()
        limit = 5 
        count = 0
        while current_superior and count < limit:
            if current_superior not in superiors:
                 superiors.append(current_superior)
            current_superior = current_superior.get_kpi_evaluator()
            count += 1
        return superiors
    

    def get_subordinates(self):
        """
        İstifadəçinin roluna əsasən ona birbaşa tabe olan bütün işçiləri qaytarır.
        Bu metod ManyToManyField ("lead") və OneToOneField ("manager") əlaqələrini
        düzgün nəzərə alır.
        """
        
        # Admin və Top Management özlərindən başqa bütün aktiv istifadəçiləri görür
        if self.role in ['admin', 'top_management']:
            return User.objects.filter(is_active=True).exclude(pk=self.pk).order_by('first_name', 'last_name')

        # Department Lead rəhbərlik etdiyi BÜTÜN departamentlərdəki işçiləri görür
        if self.role == 'department_lead':
            # "led_departments" -> Department modelindəki 'lead' sahəsinin related_name'idir
            led_departments = self.led_departments.all()
            if led_departments.exists():
                return User.objects.filter(
                    department__in=led_departments,
                    role__in=['manager', 'employee'],
                    is_active=True
                ).order_by('first_name', 'last_name')
        
        # Manager idarə etdiyi departamentdəki işçiləri görür
        if self.role == 'manager':
            try:
                # "managed_department" -> Department modelindəki 'manager' sahəsinin related_name'idir
                managed_dept = self.managed_department
                return User.objects.filter(
                    department=managed_dept,
                    role='employee',
                    is_active=True
                ).order_by('first_name', 'last_name')
            except Department.DoesNotExist:
                # Bəzən manager heç bir departamentə təyin edilməyə bilər
                return User.objects.none()

        # Digər rolların (məsələn, Employee) tabeliyində işçi yoxdur
        return User.objects.none()