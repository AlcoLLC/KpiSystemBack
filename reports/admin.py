from django.contrib import admin
from .models import ActivityLog

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'action_type', 'target_user', 'target_task')
    list_filter = ('action_type', 'timestamp', 'actor')
    search_fields = ('actor__username', 'actor__first_name', 'actor__last_name', 'details')
    readonly_fields = ('timestamp', 'actor', 'action_type', 'details', 'target_user', 'target_task')
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False