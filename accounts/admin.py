from django.contrib import admin
from .models import User, Department

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "role", "first_name", "last_name", "phone_number")
    list_filter = ("role",)
    search_fields = ('username', 'email', 'first_name', 'last_name')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "manager", "lead")