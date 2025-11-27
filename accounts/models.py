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

class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("ceo", "CEO"), # YENİ ROL
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
                # Manager, öz departamentindəki Employee'ləri ataya bilir
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
        if self.role in ["ceo", "admin"]: # YENİ: CEO və Admin'in birbaşa üstü yoxdur
            return None

        if self.department:
            if self.role == "employee":
                # İşçinin birbaşa üstü: Manager (əsas)
                manager = self.department.manager
                if manager and manager.is_active:
                    return manager
            
            # İşçi və ya Manager'ın bir sonraki üstü: Department Lead (yalnız Manager yoxdursa)
            if self.role in ["employee", "manager"]:
                lead = self.department.department_lead
                if lead and lead.is_active:
                    return lead
        
        # Əgər yuxarıdakı yoxlamalar üst rol tapmazsa (Manager/Lead yoxdursa)
        # və ya cari rol Department Lead isə
        if self.role == "department_lead":
             # D-Lead'in üstü: Top Management (Departamentinə atanmış olan)
             if self.department and self.department.top_management.exists():
                 return self.department.top_management.filter(is_active=True).first()
             
             # Əgər departamentə Top Management atanmayıbsa və ya CEO yoxlaması
             # Bu hissə Top Management-ə keçir, o da CEO-nu qaytarır (aşağıda)

        if self.role in ["employee", "manager", "department_lead", "top_management"]:
             # Hiyerarxiyada boşluq varsa və ya Top Management-in özü üçün
             
             # 1. Hiyerarxik zincir: Top Management -> CEO
             if self.role == "top_management":
                 ceo = User.objects.filter(role="ceo", is_active=True).first()
                 if ceo:
                     return ceo
             
             if self.role in ["employee", "manager", "department_lead"]:
                if self.department and self.department.top_management.exists():
                     return self.department.top_management.filter(is_active=True).first()
                
                # Növbəti mərhələ: CEO
                ceo = User.objects.filter(role="ceo", is_active=True).first()
                if ceo:
                    return ceo

        return None
    
    def get_subordinates(self):
        if self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk).order_by('first_name', 'last_name')
        
        if self.role == 'ceo': # YENİ ROL: CEO'nun astları (Admin hariç tüm aktif kullanıcılar, Top Management dahil)
            return User.objects.filter(is_active=True).exclude(
                Q(pk=self.pk) | Q(role='admin')
            ).order_by('first_name', 'last_name')

        if self.role == 'top_management':
            # Top Management'ın astları: Kendi departmanlarındaki D-Lead, Manager ve Employee'ler
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments,
                    role__in=['department_lead', 'manager', 'employee'],
                    is_active=True
                ).exclude(pk=self.pk).order_by('first_name', 'last_name')
        
        if self.role == 'department_lead':
            # Department Lead'in astları: Kendi departmanındaki Manager ve Employee'ler
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
            # Manager'ın astları: Kendi departmanındaki Employee'ler
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
        # ... (Eynidir, çünki get_direct_superior'ı istifadə edir) ...
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
        # ... (Eynidir, çünki get_kpi_evaluator'ı istifadə edir) ...
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
            # Admin, admin və ceo hariç tüm aktif kullanıcıları değerlendirebilir
            return User.objects.filter(is_active=True).exclude(
                Q(id=self.id) | Q(role__in=['admin', 'ceo'])
            )

        if self.role == 'ceo': # YENİ ROL: CEO, Top Management'ı qiymətləndirir
             return User.objects.filter(role='top_management', is_active=True)

        if not self.department:
            return User.objects.none()

        if self.role == 'top_management':
            # Top Management, kendi departmanlarındaki Department Lead'leri qiymətləndirir
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                return User.objects.filter(
                    department__in=managed_departments, 
                    role='department_lead', 
                    is_active=True
                )
        
        elif self.role == 'department_lead':
             try:
                # Department Lead, kendi departmanındaki Manager ve Employee'leri qiymətləndirir
                led_dept = self.led_department
                return User.objects.filter(department=led_dept, role__in=['manager', 'employee'], is_active=True)
             except Department.DoesNotExist:
                return User.objects.none()
        elif self.role == 'manager':
            try:
                # Manager, kendi departmanındaki Employee'leri qiymətləndirir
                managed_dept = self.managed_department
                return User.objects.filter(department=managed_dept, role='employee', is_active=True)
            except Department.DoesNotExist:
                return User.objects.none()
        
        return User.objects.none()


    def get_user_kpi_subordinates(self):
        if self.role == 'admin':
             # Admin, admin və ceo hariç tüm aktiv kullanıcıları değerlendirebilir
             return User.objects.filter(is_active=True).exclude(
                 Q(id=self.id) | Q(role__in=['admin', 'ceo'])
             )

        if self.role == 'ceo': 
             # CEO yalnız hiyerarxiyada boşluq olan işçiləri görür
             # (Top Management-i həmişə görür + boşluqdakı D-Lead, Manager, Employee)
             ceo_subordinates = User.objects.filter(is_active=True).exclude(
                 Q(pk=self.pk) | Q(role__in=['admin', 'ceo'])
             )
             
             # Top Management-i əlavə et
             result_ids = set(ceo_subordinates.filter(role='top_management').values_list('id', flat=True))
             
             # Department Lead-lər: TM-si olmayanları əlavə et
             for lead in ceo_subordinates.filter(role='department_lead'):
                 if lead.department and not lead.department.top_management.exists():
                     result_ids.add(lead.id)
             
             # Manager-lər: Department Lead-i olmayanları əlavə et
             for manager in ceo_subordinates.filter(role='manager'):
                 if manager.department and not manager.department.department_lead:
                     result_ids.add(manager.id)
             
             # Employee-lər: Manager və Department Lead-i olmayanları əlavə et
             for employee in ceo_subordinates.filter(role='employee'):
                 if employee.department:
                     if not employee.department.manager and not employee.department.department_lead:
                         result_ids.add(employee.id)
             
             return User.objects.filter(id__in=result_ids).order_by('first_name', 'last_name')

        if self.role == 'top_management':
            # Top Management yalnız öz departamentlərindəki işçiləri görür
            managed_departments = self.top_managed_departments.all()
            if managed_departments.exists():
                # SUPERIOR üçün: Department Lead
                # TM üçün: Employee və Manager
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
        """
        Qiymətləndirmə növünə görə uyğun qiymətləndiricini qaytarır.
        - SUPERIOR: Hiyerarxiyada birbaşa üst rəhbər
        - TOP_MANAGEMENT: Yalnız Employee və Manager üçün TM tərəfindən ikinci qiymətləndirmə
        """
        if self.role in ["admin", "ceo"] or not self.department:
            return None
            
        # SUPERIOR qiymətləndirməsi: Hiyerarxiyada birbaşa üst
        if evaluation_type == 'SUPERIOR':
            if self.role == 'employee':
                # Employee -> Manager (əsas) və ya Department Lead
                manager = self.department.manager
                if manager and manager.is_active:
                    return manager
                # Manager yoxdursa, Department Lead
                lead = self.department.department_lead
                if lead and lead.is_active:
                    return lead
            
            elif self.role == 'manager':
                # Manager -> Department Lead
                lead = self.department.department_lead
                if lead and lead.is_active:
                    return lead
            
            elif self.role == 'department_lead':
                # Department Lead -> Top Management
                if self.department.top_management.exists():
                    return self.department.top_management.filter(is_active=True).first()
                # TM yoxdursa, CEO
                return User.objects.filter(role='ceo', is_active=True).first()
            
            elif self.role == 'top_management': 
                # Top Management -> CEO (SUPERIOR)
                return User.objects.filter(role='ceo', is_active=True).first()
            
            # ÖNƏMLİ: Əgər yuxarıdakı şərtlər üst tapmadısa
            # (məsələn Manager var ama Department Lead yoxdur)
            # o zaman növbəti səviyyəyə keçirik
            if self.role in ['employee', 'manager']:
                # TM yoxlayırıq
                if self.department.top_management.exists():
                    return self.department.top_management.filter(is_active=True).first()
                # TM da yoxdursa, CEO
                return User.objects.filter(role='ceo', is_active=True).first()
                
        # TOP_MANAGEMENT qiymətləndirməsi: Yalnız Employee və Manager üçün
        elif evaluation_type == 'TOP_MANAGEMENT':
            if self.role in ['employee', 'manager']:
                # Employee və Manager üçün ikinci dəyərləndirmə TM tərəfindən
                if self.department and self.department.top_management.exists():
                    return self.department.top_management.filter(is_active=True).first()
            
            # Digər bütün rollar (department_lead, top_management, ceo, admin) üçün 
            # TOP_MANAGEMENT qiymətləndirməsi YOXDUR
            return None

        return None
    
    def get_kpi_evaluator(self):
        # Bu metod hiyerarxiyada bir üst qiymətləndiricini qaytarır
        # (Ənənəvi iyerarxiyaya əsaslanaraq, TOP_MANAGEMENT qiymətləndirməsinin icazəsi başqa yerdə yoxlanılacaq)
        if self.role in ["admin", "ceo"]:
            return None
        
        # 1. Employee: Manager -> Lead -> Top Management -> CEO
        if self.role == 'employee':
            if self.department and self.department.manager:
                return self.department.manager
            # Manager yoxdursa, Department Lead
            if self.department and self.department.department_lead:
                return self.department.department_lead
        
        # 2. Manager: Department Lead -> Top Management -> CEO
        elif self.role == 'manager':
            if self.department and self.department.department_lead:
                return self.department.department_lead

        # 3. Department Lead: Top Management -> CEO
        elif self.role == 'department_lead':
            if self.department and self.department.top_management.exists():
                return self.department.top_management.filter(is_active=True).first()
        
        # 4. Top Management: CEO
        elif self.role == 'top_management':
            return User.objects.filter(role='ceo', is_active=True).first()

        # Boşluq doldurucusu (Ən yüksək mümkün rəhbər)
        if self.department and self.department.top_management.exists():
             return self.department.top_management.filter(is_active=True).first()
             
        return User.objects.filter(role='ceo', is_active=True).first()