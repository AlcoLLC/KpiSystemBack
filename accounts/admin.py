from django.contrib import admin
from .models import User, Department
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

class LedDepartmentsInline(admin.TabularInline):
    model = Department.lead.through 
    verbose_name = "Rəhbərlik etdiyi departament"
    verbose_name_plural = "Rəhbərlik etdiyi departamentlər"
    extra = 1

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "username", "email", "role", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)

    def get_inlines(self, request, obj=None):
        if obj and obj.role in ['department_lead', 'top_management']:
            return [LedDepartmentsInline]
        return []

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        if obj and obj.role in ['department_lead', 'top_management']:
            additional_fields = ('role', 'profile_photo', 'phone_number')
        else:
            additional_fields = ('role', 'department', 'profile_photo', 'phone_number')
            
        return fieldsets + (('Əlavə Məlumatlar', {'fields': additional_fields}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'manager', 'display_leads')
    list_filter = ('manager',) 
    search_fields = ('name',)
    filter_horizontal = ('lead',)

    def display_leads(self, obj):
        return ", ".join([user.get_full_name() for user in obj.lead.all()])
    display_leads.short_description = 'Rəhbərlər (Leads)'