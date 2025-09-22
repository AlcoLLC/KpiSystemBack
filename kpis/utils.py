import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

def send_kpi_evaluation_request_email(kpi_evaluation):
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
    evaluation_url = f"{site_url}/pending-evaluations"

    subject = f"KPI Dəyərləndirmə Tələbi: {evaluatee.get_full_name()} - {task.title}"
    template_name = 'emails/kpi_evaluation_request.html'

    context = {
        'task': task,
        'evaluatee_name': evaluatee.get_full_name() or evaluatee.username,
        'superior_name': superior.get_full_name() or superior.username,
        'evaluation_url': evaluation_url,
        'self_score': kpi_evaluation.self_evaluation_score,  # 10 üzerinden
        'self_comment': kpi_evaluation.comment,
        'evaluation_id': kpi_evaluation.id
    }

    try:
        html_message = render_to_string(template_name, context)
        plain_message = f"""
        Salam, {superior.get_full_name() or superior.username}.
        
        '{evaluatee.get_full_name()}' adlı işçi '{task.title}' tapşırığı üçün özünü {kpi_evaluation.self_evaluation_score}/10 bal ilə qiymətləndirdi.
        
        Zəhmət olmasa siz də bu işçini 100 üzerinden qiymətləndirin.
        
        Dəyərləndirmə üçün: {evaluation_url}
        """

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
