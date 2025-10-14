from .models import ActivityLog

def create_log_entry(actor, action_type, target_user=None, target_task=None, details=None):
    ActivityLog.objects.create(
        actor=actor,
        action_type=action_type,
        target_user=target_user,
        target_task=target_task,
        details=details or {}
    )