from django.contrib import admin
from .models import User, Department, Position, FactoryPosition
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(FactoryPosition)
class FactoryPositionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class ManagedDepartmentsInline(admin.TabularInline):
    model = Department.top_management.through 
    extra = 1
    verbose_name = _("İdarə edilən Departament")
    verbose_name_plural = _("İdarə edilən Departamentlər")

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ManagedDepartmentsInline]
    
    list_display = (
        "id", "username", "first_name", "last_name", 
        "role", "factory_role", "factory_type", "department", "is_staff"
    )
    
    list_filter = (
        "role", "factory_role", "factory_type", "is_staff", 
        "department", "position", "factory_position"
    )
    
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-id',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        office_fields = ('role', 'position', 'department') 
        
        factory_fields = ('factory_role', 'factory_type', 'factory_position')
        extra_fields = ('profile_photo', 'phone_number', 'slug')

        new_fieldsets = list(fieldsets)
        new_fieldsets.append((_('Ofis Strukturu'), {'fields': office_fields}))
        new_fieldsets.append((_('Zavod Strukturu'), {'fields': factory_fields}))
        new_fieldsets.append((_('Əlavə Parametrlər'), {'fields': extra_fields}))
        
        return new_fieldsets

    readonly_fields = ('slug',)