from django.contrib import admin
from .models import User, Department, Profile


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "role")
    list_filter = ("role",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "manager", "lead")

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'email')
    search_fields = ('user__username', 'first_name', 'last_name', 'email')