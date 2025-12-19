from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
import itertools
from accounts.validators import validate_file_type
from django.db.models import Q

class Position(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Vəzifənin adı")

    class Meta:
        verbose_name = "Vəzifə"
        verbose_name_plural = "Vəzifələr"
        ordering = ['name']

    def __str__(self):
        return self.name

class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("top_management", "Zavod Direktoru"),
        ("deputy_director", "Zavod Direktoru Müavini"),
        ("department_lead", "Bölmə Rəhbəri"),
        ("employee", "İşçi"),
    ]

    FACTORY_TYPES = [
        ("dolum", "Dolum"),
        ("bidon", "Bidon"),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    factory_type = models.CharField(max_length=10, choices=FACTORY_TYPES, null=True, blank=True)
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
    slug = models.SlugField(unique=True, max_length=255, blank=True, null=True)

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

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_factory_type_display() if self.factory_type else 'Zavod seçilməyib'})"

    def get_direct_superior(self):
        if self.role in ["top_management", "admin"] or not self.factory_type:
            return None

        if self.role == "employee":
            lead = User.objects.filter(
                role="department_lead", 
                factory_type=self.factory_type, 
                is_active=True
            ).first()
            if lead: return lead
            deputy = User.objects.filter(role="deputy_director", factory_type=self.factory_type, is_active=True).first()
            if deputy: return deputy
            return User.objects.filter(role="top_management", factory_type=self.factory_type, is_active=True).first()

        if self.role == "department_lead":
            deputy = User.objects.filter(
                role="deputy_director", 
                factory_type=self.factory_type, 
                is_active=True
            ).first()
            if deputy: return deputy
            return User.objects.filter(role="top_management", factory_type=self.factory_type, is_active=True).first()

        if self.role == "deputy_director":
            return User.objects.filter(
                role="top_management", 
                factory_type=self.factory_type, 
                is_active=True
            ).first()

        return None

    def get_subordinates(self):
        if not self.factory_type or self.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=self.pk) if self.role == 'admin' else User.objects.none()

        if self.role == 'top_management':
            return User.objects.filter(factory_type=self.factory_type, is_active=True).exclude(pk=self.pk)

        if self.role == 'deputy_director':
            return User.objects.filter(
                factory_type=self.factory_type, 
                role__in=['department_lead', 'employee'],
                is_active=True
            )

        if self.role == 'department_lead':
            return User.objects.filter(
                factory_type=self.factory_type, 
                role='employee',
                is_active=True
            )

        return User.objects.none()


    def get_evaluation_config(self):
        superior = self.get_direct_superior()

        tm_evaluator = None
        if self.role == "employee":
            tm_evaluator = User.objects.filter(role="top_management", factory_type=self.factory_type, is_active=True).first()

        return {
            'requires_self': self.role not in ['admin', 'top_management'],
            'superior_evaluator': superior,
            'superior_evaluator_name': superior.get_full_name() if superior else None,
            'tm_evaluator': tm_evaluator,
            'is_dual_evaluation': tm_evaluator is not None and superior != tm_evaluator
        }