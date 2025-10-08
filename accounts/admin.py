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
    list_display = ('id', 'name', 'manager', 'display_leads')
    list_filter = ('manager',) 
    search_fields = ('name',)
    filter_horizontal = ('lead',)

    def display_leads(self, obj):
        return ", ".join([user.get_full_name() for user in obj.lead.all()])
    display_leads.short_description = 'Rəhbərlər (Leads)'