import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.core.signing import Signer

logger = logging.getLogger(__name__)


def send_kpi_evaluation_request_email(kpi_evaluation):
    """
    Kullanıcı öz değerlendirme yaptıktan sonra üstlerine e-posta gönderir.
    """
    evaluatee = kpi_evaluation.evaluatee
    task = kpi_evaluation.task
    superior = evaluatee.get_superior()

    if not superior:
        logger.warning(f"ID {evaluatee.id} olan istifadəçinin rəhbəri tapılmadı. KPI e-poçtu göndərilmədi.")
        return

    if not superior.email:
        logger.warning(f"Rəhbərin (ID: {superior.id}) e-poçt ünvanı yoxdur. E-poçt göndərilmədi.")
        return

    site_url = getattr(settings, "FRONTEND_URL", "http://91.99.112.51/kpi_system") 

    evaluation_url = f"{site_url}/"

    subject = f"KPI Dəyərləndirmə Tələbi: {evaluatee.get_full_name()} - {task.title}"
    template_name = 'emails/kpi_evaluation_request.html'

    context = {
        'task': task,
        'evaluatee_name': evaluatee.get_full_name() or evaluatee.username,
        'superior_name': superior.get_full_name() or superior.username,
        'evaluation_url': evaluation_url,
        'self_score': kpi_evaluation.score, 
        'self_comment': kpi_evaluation.comment 
    }

    try:
        html_message = render_to_string(template_name, context)
        plain_message = f"Salam, {superior.username}. Zəhmət olmasa '{evaluatee.get_full_name()}' adlı işçinin '{task.title}' tapşırığı üçün KPI dəyərləndirməsini tamamlayın."

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[superior.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"KPI dəyərləndirmə e-poçtu uğurla {superior.email} ünvanına göndərildi.")
    except Exception as e:
        logger.error(f"KPI e-poçtu göndərilərkən xəta baş verdi (Alıcı: {superior.email}): {str(e)}", exc_info=True)