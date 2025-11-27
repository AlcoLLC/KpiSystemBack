# kpi-system-backend\kpis\utils.py

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import KPIEvaluation # Import əlavə edildi

logger = logging.getLogger(__name__)

def send_kpi_evaluation_request_email(kpi_evaluation):
    """
    KPI dəyərləndirmə sorğusu e-poçtu göndərir. 
    Self Evaluation tamamlandıqda dərhal rəhbərə, 
    Superior Evaluation tamamlandıqda isə Top Management-ə (əgər icazəlidirsə) göndərir.
    """
    evaluatee = kpi_evaluation.evaluatee
    task = kpi_evaluation.task
    
    # 1. Bildirişi kim almalıdır?
    recipient = None
    email_type = ""
    
    # Əgər cari qiymətləndirmə SELF_EVALUATION idisə, növbəti addım dərhal üst rəhbərdir.
    if kpi_evaluation.evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
        recipient = evaluatee.get_direct_superior()
        email_type = "superior"
    
    # Əgər cari qiymətləndirmə SUPERIOR_EVALUATION idisə, növbəti addım Top Management ola bilər.
    elif kpi_evaluation.evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
        # Yalnız Manager və Employee qiymətləndirilirsə, Top Management-i tapırıq
        if evaluatee.role in ['manager', 'employee']:
             
            # Evaluatee-nin departamentinə təyin olunmuş Top Management-i tap
            top_management_users = evaluatee.department.top_management.all() if evaluatee.department else []
            
            # Əgər birdən çox Top Management varsa, siyahı olaraq işləyəcək, amma indilik yalnız birincisini götürürük
            # Çoxsaylı Top Management userlərinə göndərmək üçün recipient siyahı olmalıdır
            if top_management_users.exists():
                recipient = top_management_users.first()
                email_type = "top_management"

    # Əgər recipient tapılmayıbsa (və ya Top Management növbəti qiymətləndirici deyilsə)
    if not recipient:
        logger.warning(
            f"ID {evaluatee.id} olan istifadəçinin növbəti rəhbəri tapılmadı (Type: {kpi_evaluation.evaluation_type}). KPI e-poçtu göndərilmədi."
        )
        return

    # 2. E-poçt parametrlərini hazırla
    if not recipient.email:
        logger.warning(f"Rəhbərin (ID: {recipient.id}) e-poçt ünvanı yoxdur. E-poçt göndərilmədi.")
        return

    site_url = getattr(settings, "FRONTEND_URL", "https://metrics.azlub.com/kpi_system") 
    evaluation_url = f"{site_url}/"

    subject = f"KPI Dəyərləndirmə Tələbi ({email_type.upper()}): {evaluatee.get_full_name()} - {task.title}"
    template_name = 'emails/kpi_evaluation_request.html'

    context = {
        'task': task,
        'evaluatee_name': evaluatee.get_full_name() or evaluatee.username,
        'superior_name': recipient.get_full_name() or recipient.username,
        'evaluation_url': evaluation_url,
        
        # Self-evaluation məlumatları
        'self_score': None,
        'self_comment': None,
        'attachment_url': None,
        
        # Növbəti qiymətləndirici kimdir
        'email_type': email_type, 
        'is_top_management_email': email_type == "top_management", 
    }
    
    # Self-evaluation skorunu əldə et (bütün rəhbərlər görməlidir)
    self_eval = KPIEvaluation.objects.filter(
        task=task,
        evaluatee=evaluatee,
        evaluation_type=KPIEvaluation.EvaluationType.SELF_EVALUATION
    ).first()
    
    if self_eval:
        context['self_score'] = self_eval.self_score
        context['self_comment'] = self_eval.comment
        context['attachment_url'] = self_eval.attachment.url if self_eval.attachment else None
        
    # Əgər Top Management-ə göndərilirsə, Superior-un qiymətləndirməsini də əlavə et
    superior_eval = None
    if email_type == "top_management":
         superior_eval = KPIEvaluation.objects.filter(
            task=task,
            evaluatee=evaluatee,
            evaluation_type=KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
         ).first()
         
         if superior_eval:
              context['superior_score'] = superior_eval.superior_score
              context['superior_comment'] = superior_eval.comment

    # 3. E-poçtu göndər
    try:
        html_message = render_to_string(template_name, context)
        plain_message = f"Salam, {recipient.username}. Zəhmət olmasa '{evaluatee.get_full_name()}' adlı işçinin '{task.title}' tapşırığı üçün KPI dəyərləndirməsini tamamlayın."

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[recipient.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"KPI dəyərləndirmə e-poçtu uğurla {recipient.email} ünvanına göndərildi (Type: {email_type}).")
    except Exception as e:
        logger.error(f"KPI e-poçtu göndərilərkən xəta baş verdi (Alıcı: {recipient.email}): {str(e)}", exc_info=True)