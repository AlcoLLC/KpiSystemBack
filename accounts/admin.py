from django.contrib import admin
from .models import User, Department, Position
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "username", "email", 'position', "role", "department", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", 'position', "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)


    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        # GÜNCELLENDİ: CEO ve Top Management rollerine sahip kullanıcılar için 'department' alanı gizlenir.
        if obj and obj.role in ['ceo', 'top_management']:
            additional_fields = ('role', 'profile_photo', 'phone_number', 'position')
        else:
            # Diğer roller (employee, manager, department_lead, admin) için 'department' gösterilir.
            additional_fields = ('role', 'department', 'profile_photo', 'phone_number', 'position')
            
        return fieldsets + (('Əlavə Məlumatlar', {'fields': additional_fields}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    # GÜNCELLENDİ: 'ceo' alanı list_display'a eklendi.
    list_display = ('id', 'name', 'ceo', 'manager', 'department_lead', 'display_top_management')
    list_filter = ('manager', 'department_lead', 'ceo')  
    search_fields = ('name',)
    
    filter_horizontal = ('top_management',)

    def display_top_management(self, obj):
        # top_management alanındaki kullanıcıların tam adlarını virgülle ayırarak gösterir
        return ", ".join([user.get_full_name() for user in obj.top_management.all()])
    display_top_management.short_description = 'Üst Rəhbərlik (Top Management)'