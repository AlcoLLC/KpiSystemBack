from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "assignee", "created_by", "status", "priority", "approved", "created_at")
    list_filter = ("status", "priority", "approved", "created_at")
    search_fields = ("title", "description", "assignee__username")

