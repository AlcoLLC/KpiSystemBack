from django.contrib import admin
from .models import User, Department
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Əlavə Məlumatlar', {'fields': ('role', 'department', 'profile_photo', 'phone_number')}),
    )
    
    # Siyahıda görünəcək sahələr
    list_display = ("id", "username", "email", "role", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "manager", "lead")