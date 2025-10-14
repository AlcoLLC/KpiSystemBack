from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class ActivityLog(models.Model):
    class ActionTypes(models.TextChoices):
        TASK_CREATED = 'TASK_CREATED', _('Tapşırıq yaradıldı')
        TASK_STATUS_CHANGED = 'TASK_STATUS_CHANGED', _('Tapşırığın statusu dəyişdirildi')
        TASK_APPROVED = 'TASK_APPROVED', _('Tapşırıq təsdiqləndi')
        KPI_TASK_EVALUATED = 'KPI_TASK_EVALUATED', _('Tapşırıq üzrə KPI qiymətləndirildi')
        KPI_USER_EVALUATED = 'KPI_USER_EVALUATED', _('Aylıq KPI qiymətləndirildi')

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name=_("Fəaliyyəti icra edən")
    )
    action_type = models.CharField(
        max_length=50,
        choices=ActionTypes.choices,
        verbose_name=_("Fəaliyyət növü")
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Detallar")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Tarix")
    )
    
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='targeted_in_logs',
        verbose_name=_("Hədəf istifadəçi")
    )
    target_task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activity_logs',
        verbose_name=_("Hədəf tapşırıq")
    )
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = _("Fəaliyyət Tarixçəsi")
        verbose_name_plural = _("Fəaliyyət Tarixçələri")

    def __str__(self):
        return f"{self.actor} - {self.get_action_type_display()} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"