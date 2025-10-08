from django.contrib import admin
from .models import User, Department
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

class LedDepartmentsInline(admin.TabularInline):
    model = Department.lead.through  # ManyToMany əlaqəsinin aralıq cədvəlini istifadə edir
    verbose_name = "Rəhbərlik etdiyi departament"
    verbose_name_plural = "Rəhbərlik etdiyi departamentlər"
    extra = 1

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Əlavə Məlumatlar', {'fields': ('role', 'department', 'profile_photo', 'phone_number')}),
    )

    inlines = [LedDepartmentsInline]
    
    # Siyahıda görünəcək sahələr
    list_display = ("id", "username", "email", "role", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'manager', 'display_leads')
    list_filter = ('manager',) 
    search_fields = ('name',)
    filter_horizontal = ('lead',)

    def display_leads(self, obj):
        return ", ".join([user.get_full_name() for user in obj.lead.all()])
    display_leads.short_description = 'Rəhbərlər (Leads)'