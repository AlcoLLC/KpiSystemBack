from django.contrib import admin
from .models import User, Department, Position
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "username", "email", 'position', "role","department", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", 'position', "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)


    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        if obj and obj.role == 'ceo':
            additional_fields = ('role', 'profile_photo', 'phone_number', 'position', 'ceo_managed_departments')
        elif obj and obj.role == 'top_management': 
            additional_fields = ('role', 'profile_photo', 'phone_number', 'position', 'top_managed_departments')
        else:
            additional_fields = ('role', 'department', 'profile_photo', 'phone_number', 'position')
            
        return fieldsets + (('Əlavə Məlumatlar', {'fields': additional_fields}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'manager', 'department_lead', 'display_top_management', 'display_ceo')
    list_filter = ('manager', 'department_lead') 
    search_fields = ('name',)
    
    filter_horizontal = ('top_management', 'ceo')

    def display_top_management(self, obj):
        return ", ".join([user.get_full_name() for user in obj.top_management.all()])
    display_top_management.short_description = 'Üst Rəhbərlik (Top Management)'

    def display_ceo(self, obj):
        return ", ".join([user.get_full_name() for user in obj.ceo.all()])
    display_ceo.short_description = 'CEO'