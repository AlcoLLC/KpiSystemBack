# users/admin.py

from django.contrib import admin
from .models import User, Department
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

# DƏYİŞİKLİK 1: LedDepartmentsInline artıq lazımsızdır, silinir.
# class LedDepartmentsInline(admin.TabularInline): ...

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "username", "email", "role", "first_name", "last_name", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "groups")
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('id',)

    # DƏYİŞİKLİK 2: get_inlines metodu silinir, çünki inline istifadə etmirik.
    # def get_inlines(self, request, obj=None): ...

    # Bu metod istəyə bağlı olaraq qala bilər, department sahəsini bəzi rollar üçün gizlədir.
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        
        # Top Management və Admin birbaşa departamentə bağlı olmadığı üçün bu sahəni gizlətmək məntiqlidir
        if obj and obj.role in ['top_management', 'admin']:
            additional_fields = ('role', 'profile_photo', 'phone_number')
        else:
            additional_fields = ('role', 'department', 'profile_photo', 'phone_number')
            
        return fieldsets + (('Əlavə Məlumatlar', {'fields': additional_fields}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    # DƏYİŞİKLİK 3: list_display yeni sahələri göstərmək üçün yeniləndi.
    list_display = ('id', 'name', 'manager', 'department_lead', 'display_top_management')
    list_filter = ('manager', 'department_lead') 
    search_fields = ('name',)
    
    # DƏYİŞİKLİK 4: filter_horizontal 'lead' yerinə 'top_management' üçün istifadə olunur.
    filter_horizontal = ('top_management',)

    # DƏYİŞİKLİK 5: 'display_leads' metodu 'display_top_management' ilə əvəz edildi.
    def display_top_management(self, obj):
        return ", ".join([user.get_full_name() for user in obj.top_management.all()])
    display_top_management.short_description = 'Üst Rəhbərlik (Top Management)'