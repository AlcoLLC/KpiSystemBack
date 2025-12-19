from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
import itertools
from .validators import validate_file_type
from django.db.models import Q

class Department(models.Model):
    name = models.CharField(max_length=255)
    ceo = models.OneToOneField(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ceo_department",
        limit_choices_to={'role': 'ceo'}
    )
    
    manager = models.OneToOneField(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="managed_department",
        limit_choices_to={'role': 'manager'}
    )

    department_lead = models.OneToOneField(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_department',
        limit_choices_to={'role': 'department_lead'}
    )

    top_management = models.ManyToManyField(
        'User',
        blank=True,
        related_name='top_managed_departments',
        limit_choices_to={'role': 'top_management'}
    )

    def __str__(self):
        return self.name

class Position(models.Model):
    name = models.CharField(
        max_length=255, 
        unique=True, 
        verbose_name="Vəzifənin adı"
    )

    class Meta:
        verbose_name = "Vəzifə"
        verbose_name_plural = "Vəzifələr"
        ordering = ['name']

    def __str__(self):
        return self.name
    
class FactoryPosition(models.Model):
    name = models.CharField(
        max_length=255, 
        unique=True, 
        verbose_name="Vəzifənin adı (Zavod)"
    )

    class Meta:
        verbose_name = "Zavod Vəzifəsi"
        verbose_name_plural = "Zavod Vəzifələri"
        ordering = ['name']

    def __str__(self):
        return self.name

class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("ceo", "CEO"),
        ("top_management", "Yuxarı İdarəetmə"),
        ("department_lead", "Departament Rəhbəri"),
        ("manager", "Menecer"),
        ("employee", "İşçi"),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    profile_photo = models.FileField(
        upload_to='profile_photos/', 
        null=True, 
        blank=True,
        validators=[validate_file_type] 
    )
    phone_number = models.CharField(max_length=20, blank=True)

    position = models.ForeignKey(
            Position, 
            on_delete=models.SET_NULL,
            null=True, 
            blank=True,
            related_name='users',
            verbose_name="Vəzifə"
    )

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
        role_hierarchy = {
            "employee": "Manager or Department Lead",
            "manager": "Department Lead",
            "department_lead": "Top Management",
            "top_management": "CEO",
            "ceo": "N/A",
            "admin": "N/A",
        }
        return role_hierarchy.get(self.role, "Unknown")
    
    def get_superior(self):
        if self.role == "employee":
            if not self.department:
                return None
            return self.department.manager or self.department.department_lead

        elif self.role == "manager":
            if self.department:
                return self.department.department_lead
            return None

        elif self.role == "department_lead":
            return User.objects.filter(role="top_management").first()
        
        elif self.role == "top_management": 
            return User.objects.filter(role="ceo").first()

        else:
            return None
        
    def get_assignable_users(self):
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk)
        
        if self.role == "ceo": 
            return User.objects.filter(role="top_management", is_active=True)

        if self.role == "top_management":
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments,
                    role__in=["department_lead"],       
                    is_active=True
                )
            return User.objects.none()
        
        if not self.department:
            return User.objects.none()

        if self.role == "department_lead":
            try:
                led_dept = self.led_department
                return User.objects.filter(
                    department=led_dept,
                    role__in=["manager", "employee"],
                    is_active=True
                )
            except Department.DoesNotExist:
                return User.objects.none()
            
        if self.role == "manager":
            try:
                managed_dept = self.managed_department
                return User.objects.filter(
                    department=managed_dept,
                    role="employee",
                    is_active=True
                )
            except Department.DoesNotExist:
                return User.objects.none()
            
        return User.objects.none()

    def get_direct_superior(self):
        if self.role in ["ceo", "admin"]:
            return None

        if self.department:
            if self.role == "employee":
                manager = self.department.manager
                if manager and manager.is_active:
                    return manager
            
            if self.role in ["employee", "manager"]:
                lead = self.department.department_lead
                if lead and lead.is_active:
                    return lead
        
        if self.role == "department_lead":
             if self.department and self.department.top_management.exists():
                 return self.department.top_management.filter(is_active=True).first()
             

        if self.role in ["employee", "manager", "department_lead", "top_management"]:
             if self.role == "top_management":
                 ceo = User.objects.filter(role="ceo", is_active=True).first()
                 if ceo:
                     return ceo
             
             if self.role in ["employee", "manager", "department_lead"]:
                if self.department and self.department.top_management.exists():
                     return self.department.top_management.filter(is_active=True).first()
                
                ceo = User.objects.filter(role="ceo", is_active=True).first()
                if ceo:
                    return ceo

        return None
    
    def get_subordinates(self):
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk).order_by('first_name', 'last_name')
        
        if self.role == 'ceo': 
            return User.objects.filter(is_active=True).exclude(
                Q(pk=self.pk) | Q(role='admin')
            ).order_by('first_name', 'last_name')

        if self.role == 'top_management':
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments,
                    role__in=['department_lead', 'manager', 'employee'],
                    is_active=True
                ).exclude(pk=self.pk).order_by('first_name', 'last_name')
        
        if self.role == 'department_lead':
            try:
                led_dept = self.led_department 
                return User.objects.filter(
                    department=led_dept,
                    role__in=['manager', 'employee'],
                    is_active=True
                ).order_by('first_name', 'last_name')
            except Department.DoesNotExist:
                return User.objects.none()

        if self.role == 'manager':
            try:
                managed_dept = self.managed_department
                return User.objects.filter(
                    department=managed_dept,
                    role='employee',
                    is_active=True
                ).order_by('first_name', 'last_name')
            except Department.DoesNotExist:
                return User.objects.none()

        return User.objects.none()
    

    def get_all_superiors(self):
        superiors = []
        current_superior = self.get_direct_superior()
        limit = 10 
        count = 0
        while current_superior and count < limit:
            superiors.append(current_superior)
            if current_superior.pk == self.pk:
                break
            current_superior = current_superior.get_direct_superior()
            count += 1
        return superiors
    

    def get_kpi_superiors(self):
        superiors = []
        current_superior = self.get_kpi_evaluator()
        limit = 5 
        count = 0
        while current_superior and count < limit:
            if current_superior not in superiors:
                 superiors.append(current_superior)
                 if current_superior.pk == self.pk:
                    break
            current_superior = current_superior.get_kpi_evaluator()
            count += 1
        return superiors
    

    def get_kpi_subordinates(self):
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(
                Q(id=self.id) | Q(role__in=['admin', 'ceo'])
            )

        if self.role == 'ceo':
             return User.objects.filter(role='top_management', is_active=True)

        if not self.department:
            return User.objects.none()

        if self.role == 'top_management':
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments, 
                    role='department_lead', 
                    is_active=True
                )
        
        elif self.role == 'department_lead':
             try:
                led_dept = self.led_department
                return User.objects.filter(department=led_dept, role__in=['manager', 'employee'], is_active=True)
             except Department.DoesNotExist:
                return User.objects.none()
        elif self.role == 'manager':
            try:
                managed_dept = self.managed_department
                return User.objects.filter(department=managed_dept, role='employee', is_active=True)
            except Department.DoesNotExist:
                return User.objects.none()
        
        return User.objects.none()


    def get_user_kpi_subordinates(self):
        if self.role == 'admin':
             return User.objects.filter(is_active=True).exclude(
                 Q(id=self.id) | Q(role__in=['admin', 'ceo'])
             )

        if self.role == 'ceo': 
             ceo_subordinates = User.objects.filter(is_active=True).exclude(
                 Q(pk=self.pk) | Q(role__in=['admin', 'ceo'])
             )
             
             result_ids = set(ceo_subordinates.filter(role='top_management').values_list('id', flat=True))
             
             for lead in ceo_subordinates.filter(role='department_lead'):
                 if lead.department and not lead.department.top_management.exists():
                     result_ids.add(lead.id)
             
             for manager in ceo_subordinates.filter(role='manager'):
                 if manager.department and not manager.department.department_lead:
                     result_ids.add(manager.id)
             
             for employee in ceo_subordinates.filter(role='employee'):
                 if employee.department:
                     if not employee.department.manager and not employee.department.department_lead:
                         result_ids.add(employee.id)
             
             return User.objects.filter(id__in=result_ids).order_by('first_name', 'last_name')

        if self.role == 'top_management':
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments,
                    role__in=['department_lead', 'manager', 'employee'],
                    is_active=True
                ).exclude(pk=self.pk).order_by('first_name', 'last_name')
            return User.objects.none()
        
        if self.role == 'department_lead':
            try:
                led_dept = self.led_department 
                return User.objects.filter(
                    department=led_dept,
                    role__in=['manager', 'employee'],
                    is_active=True
                ).order_by('first_name', 'last_name')
            except Department.DoesNotExist:
                return User.objects.none()

        if self.role == 'manager':
            try:
                managed_dept = self.managed_department
                return User.objects.filter(
                    department=managed_dept,
                    role='employee',
                    is_active=True
                ).order_by('first_name', 'last_name')
            except Department.DoesNotExist:
                return User.objects.none()

        return User.objects.none()
    
    def get_kpi_evaluator_by_type(self, evaluation_type):
        if self.role in ["admin", "ceo"] or not self.department:
            return None
        
        def find_next_available_superior(user):
            if user.role == 'employee':
                if user.department.manager and user.department.manager.is_active:
                    return user.department.manager
                if user.department.department_lead and user.department.department_lead.is_active:
                    return user.department.department_lead
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'manager':
                if user.department.department_lead and user.department.department_lead.is_active:
                    return user.department.department_lead
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'department_lead':
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'top_management':
                return User.objects.filter(role='ceo', is_active=True).first()
            
            return None

        if evaluation_type == 'SUPERIOR':
            superior = find_next_available_superior(self)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[get_kpi_evaluator_by_type] {self.get_full_name()} ({self.role}) -> SUPERIOR: {superior.get_full_name() if superior else 'None'} ({superior.role if superior else 'N/A'})")
            return superior
        
        elif evaluation_type == 'TOP_MANAGEMENT':
            if self.role not in ['employee', 'manager']:
                return None
            
            superior = find_next_available_superior(self)
            
            if superior and superior.role in ['manager', 'department_lead']:
                if self.department and self.department.top_management.exists():
                    tm = self.department.top_management.filter(is_active=True).first()
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"[get_kpi_evaluator_by_type] {self.get_full_name()} ({self.role}) -> TOP_MANAGEMENT: {tm.get_full_name() if tm else 'None'} (SUPERIOR is {superior.role})")
                    return tm
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[get_kpi_evaluator_by_type] {self.get_full_name()} ({self.role}) -> TOP_MANAGEMENT: None (SUPERIOR is {superior.role if superior else 'N/A'})")
            return None

        return None
    
    def get_kpi_evaluator_by_type_task(self, evaluation_type):
        if self.role in ["admin", "ceo"] or not self.department:
            return None
        
        def find_next_available_superior(user):
            """Birbaşa üst rəhbəri tapır"""
            if user.role == 'employee':
                if user.department.manager and user.department.manager.is_active:
                    return user.department.manager
                if user.department.department_lead and user.department.department_lead.is_active:
                    return user.department.department_lead
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'manager':
                if user.department.department_lead and user.department.department_lead.is_active:
                    return user.department.department_lead
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'department_lead':
                if user.department.top_management.exists():
                    return user.department.top_management.filter(is_active=True).first()
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif user.role == 'top_management':
                return User.objects.filter(role='ceo', is_active=True).first()
            
            return None

        if evaluation_type == 'SUPERIOR':
            superior = find_next_available_superior(self)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[get_kpi_evaluator_by_type_task] {self.get_full_name()} ({self.role}) -> SUPERIOR: {superior.get_full_name() if superior else 'None'} ({superior.role if superior else 'N/A'})")
            return superior
        
        elif evaluation_type == 'TOP_MANAGEMENT':
            # Yalnız employee və manager üçün Top Management dəyərləndirməsi
            if self.role not in ['employee', 'manager']:
                return None
            
            # Department-də Top Management olmalıdır
            if self.department and self.department.top_management.exists():
                tm = self.department.top_management.filter(is_active=True).first()
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[get_kpi_evaluator_by_type_task] {self.get_full_name()} ({self.role}) -> TOP_MANAGEMENT: {tm.get_full_name() if tm else 'None'}")
                return tm
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[get_kpi_evaluator_by_type_task] {self.get_full_name()} ({self.role}) -> TOP_MANAGEMENT: None (No TM in department)")
            return None

        return None

    def get_kpi_evaluator(self):
        if self.role in ["admin", "ceo"]:
            return None
        
        if self.role == 'employee':
            if self.department and self.department.manager:
                return self.department.manager
            if self.department and self.department.department_lead:
                return self.department.department_lead
        
        elif self.role == 'manager':
            if self.department and self.department.department_lead:
                return self.department.department_lead

        elif self.role == 'department_lead':
            if self.department and self.department.top_management.exists():
                return self.department.top_management.filter(is_active=True).first()
        
        elif self.role == 'top_management':
            return User.objects.filter(role='ceo', is_active=True).first()

        if self.department and self.department.top_management.exists():
             return self.department.top_management.filter(is_active=True).first()
             
        return User.objects.filter(role='ceo', is_active=True).first()
    
    def needs_dual_evaluation(self):
        if self.role not in ['employee', 'manager']:
            return False
        
        if not self.department:
            return False
        
        superior = self.get_kpi_evaluator_by_type('SUPERIOR')
        if not superior:
            return False
        
        if superior.role in ['manager', 'department_lead']:
            has_tm = self.department.top_management.exists()
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[needs_dual_evaluation] {self.get_full_name()} ({self.role}) -> {has_tm} (SUPERIOR: {superior.role}, TM exists: {has_tm})")
            return has_tm
        
        return False
    
    def needs_dual_evaluation_task(self):
        if self.role not in ['employee', 'manager']:
            return False
        
        if not self.department:
            return False
        
        has_tm = self.department.top_management.exists()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[needs_dual_evaluation_task] {self.get_full_name()} ({self.role}) -> {has_tm} (TM exists: {has_tm})")
        
        return has_tm

    def get_evaluation_config(self):
        if self.role in ['admin', 'ceo']:
            return {
                'requires_self': False,
                'superior_evaluator': None,
                'superior_evaluator_name': None,
                'tm_evaluator': None,
                'tm_evaluator_name': None,
                'is_dual_evaluation': False
            }
        
        superior = self.get_kpi_evaluator_by_type('SUPERIOR')
        tm_evaluator = self.get_kpi_evaluator_by_type('TOP_MANAGEMENT')
        is_dual = self.needs_dual_evaluation()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[get_evaluation_config] {self.get_full_name()} ({self.role}) -> Superior: {superior.get_full_name() if superior else 'None'}, TM: {tm_evaluator.get_full_name() if tm_evaluator else 'None'}, Dual: {is_dual}")
        
        return {
            'requires_self': True,
            'superior_evaluator': superior,
            'superior_evaluator_name': superior.get_full_name() if superior else None,
            'tm_evaluator': tm_evaluator,
            'tm_evaluator_name': tm_evaluator.get_full_name() if tm_evaluator else None,
            'is_dual_evaluation': is_dual
        }
    
    def get_evaluation_config_task(self):
        """Dəyərləndirmə konfiqurasiyasını qaytarır"""
        if self.role in ['admin', 'ceo']:
            return {
                'requires_self': False,
                'superior_evaluator': None,
                'superior_evaluator_name': None,
                'superior_evaluator_id': None,
                'tm_evaluator': None,
                'tm_evaluator_name': None,
                'tm_evaluator_id': None,
                'is_dual_evaluation': False
            }
        
        superior = self.get_kpi_evaluator_by_type_task('SUPERIOR')
        tm_evaluator = self.get_kpi_evaluator_by_type_task('TOP_MANAGEMENT')
        is_dual = self.needs_dual_evaluation_task()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[get_evaluation_config] {self.get_full_name()} ({self.role}) -> Superior: {superior.get_full_name() if superior else 'None'}, TM: {tm_evaluator.get_full_name() if tm_evaluator else 'None'}, Dual: {is_dual}")
        
        return {
            'requires_self': True,
            'superior_evaluator': superior,
            'superior_evaluator_name': superior.get_full_name() if superior else None,
            'superior_evaluator_id': superior.id if superior else None,
            'tm_evaluator': tm_evaluator,
            'tm_evaluator_name': tm_evaluator.get_full_name() if tm_evaluator else None,
            'tm_evaluator_id': tm_evaluator.id if tm_evaluator else None,
            'is_dual_evaluation': is_dual
        }


