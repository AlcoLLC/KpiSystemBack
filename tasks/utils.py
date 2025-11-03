import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.core.signing import Signer

logger = logging.getLogger(__name__)

def send_task_notification_email(task, notification_type):
    
    recipient = None
    subject = ""
    context = {}
    template_name = ""

    site_url = getattr(settings, "SITE_URL", "https://metrics.azlub.com/")

    if notification_type == 'new_assignment':
        recipient = task.assignee
        subject = f"Yeni Tapşırıq Təyin Edildi: {task.title}"
        template_name = 'emails/new_task_assignment.html'
        context = {
            'task': task,
            'recipient_name': recipient.get_full_name() or recipient.username,
            'site_url': site_url,
        }

    elif notification_type == 'approval_request':
        superior = task.created_by.get_superior()
        if not superior:
            logger.warning(f"ID {task.created_by.id} olan istifadəçinin təsdiq edəcək rəhbəri tapılmadı.")
            return

        recipient = superior
        subject = f"Təsdiq Gözləyən Tapşırıq: {task.title}"
        template_name = 'emails/task_approval_request.html'

        signer = Signer()
        approval_token = signer.sign_object({'task_id': task.id, 'action': 'approve'})
        rejection_token = signer.sign_object({'task_id': task.id, 'action': 'reject'})
        
        approve_url = site_url + reverse('task-verify', kwargs={'token': approval_token})
        reject_url = site_url + reverse('task-verify', kwargs={'token': rejection_token})

        context = {
            'task': task,
            'superior_name': superior.get_full_name() or superior.username,
            'creator_name': task.created_by.get_full_name() or task.created_by.username,
            'approve_url': approve_url,
            'reject_url': reject_url,
        }

    else:
        logger.error(f"Naməlum bildiriş növü: {notification_type}")
        return

    if not recipient or not recipient.email:
        logger.warning(f"ID {recipient.id} olan alıcının e-poçt ünvanı yoxdur. E-poçt göndərilmədi.")
        return

    try:
        html_message = render_to_string(template_name, context)
        
        plain_message = f"Salam, {recipient.username}. '{task.title}' adlı tapşırıqla bağlı yeni bir bildirişiniz var. Zəhmət olmasa sistemə daxil olun."

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[recipient.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"'{notification_type}' tipli e-poçt uğurla {recipient.email} ünvanına göndərildi.")

    except Exception as e:
        logger.error(f"E-poçt göndərilərkən xəta baş verdi (Alıcı: {recipient.email}): {str(e)}", exc_info=True)