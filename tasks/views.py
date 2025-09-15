import logging
from django.db.models import Q
from django.core.signing import Signer, BadSignature
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, views, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer
from .utils import send_task_notification_email

logger = logging.getLogger(__name__)

class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == "admin":
            return Task.objects.all().order_by('-created_at')
         
        return Task.objects.filter(
            Q(assignee=user) | Q(created_by=user)
        ).distinct().order_by('-created_at')

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]
        
        logger.info(f"Task yaratma cəhdi - Creator: {creator.username} (ID: {creator.id}), Assignee: {assignee.username} (ID: {assignee.id})")

        try:
            # 1. İstifadəçi özünə tapşırıq təyin edirsə
            if creator == assignee:
                logger.info(f"Creator və assignee eynidir: {creator.username}")
                superior = creator.get_superior()
                if superior:
                    task = serializer.save(created_by=creator, approved=False)
                    logger.info(f"Task yaradıldı və təsdiq üçün göndərildi. Task ID: {task.id}")
                    send_task_notification_email(task, notification_type='approval_request')
                else:
                    task = serializer.save(created_by=creator, approved=True)
                    logger.info(f"Task yaradıldı və avtomatik təsdiqləndi. Task ID: {task.id}")
                return

            # 2. İstifadəçi başqasına tapşırıq təyin edirsə
            if assignee.role == "employee":
                logger.info(f"Employee-ə task təyin edilir: {assignee.username}")
                if not assignee.department:
                    logger.error(f"Employee {assignee.username} heç bir departmentə aid deyil")
                    raise ValidationError("The assigned employee does not belong to any department.")
                    
                department = assignee.department
                designated_creator = department.manager or department.lead
                if not designated_creator:
                    logger.error(f"Department '{department.name}' üçün manager və ya lead tapılmadı")
                    raise ValidationError(f"The department '{department.name}' has no assigned Manager or Lead.")
                    
                if creator != designated_creator:
                    logger.error(f"İcazəsiz task yaratma cəhdi. Creator: {creator.username}, Designated: {designated_creator.username}")
                    raise PermissionDenied(f"You are not the designated manager or lead for this employee's department.")
                 
                task = serializer.save(created_by=creator, approved=False)
                logger.info(f"Employee üçün task yaradıldı. Task ID: {task.id}")
                send_task_notification_email(task, notification_type='new_assignment')
                return

            elif assignee.role == "manager":
                logger.info(f"Manager-ə task təyin edilir: {assignee.username}")
                if creator.role != "department_lead":
                    logger.error(f"Yalnız Department Lead manager-ə task təyin edə bilər. Creator role: {creator.role}")
                    raise PermissionDenied("Only Department Leads can assign tasks to Managers.")
                task = serializer.save(created_by=creator, approved=False)
                logger.info(f"Manager üçün task yaradıldı. Task ID: {task.id}")
                send_task_notification_email(task, notification_type='assignment_acceptance_request')
                return

            elif assignee.role == "department_lead":
                logger.info(f"Department Lead-ə task təyin edilir: {assignee.username}")
                if creator.role != "top_management":
                    logger.error(f"Yalnız Top Management department lead-ə task təyin edə bilər. Creator role: {creator.role}")
                    raise PermissionDenied("Only Top Management can assign tasks to Department Leads.")
                task = serializer.save(created_by=creator, approved=False)
                logger.info(f"Department Lead üçün task yaradıldı. Task ID: {task.id}")
                send_task_notification_email(task, notification_type='assignment_acceptance_request')
                return
                 
            elif assignee.role == "top_management":
                logger.info(f"Top Management-ə task təyin edilir: {assignee.username}")
                if creator.role != "department_lead":
                    logger.error(f"Yalnız Department Lead top management-ə task təyin edə bilər. Creator role: {creator.role}")
                    raise PermissionDenied("Only Department Leads can create tasks for Top Management.")
             
            elif assignee.role == "admin":
                logger.error(f"Admin roluna task təyin etmək cəhdi")
                raise PermissionDenied("You cannot assign tasks to a user with the admin role.")

            task = serializer.save(created_by=creator, approved=False)
            logger.info(f"Ümumi task yaradıldı. Task ID: {task.id}")
            send_task_notification_email(task, notification_type='new_assignment')
            
        except Exception as e:
            logger.error(f"Task yaratma zamanı xəta: {str(e)}", exc_info=True)
            raise


class TaskVerificationView(views.APIView):
    permission_classes = [permissions.AllowAny] 

    def get(self, request, token, *args, **kwargs):
        signer = Signer()
        try:
            data = signer.unsign_object(token)
            task_id = data['task_id']
            action = data['action']

            task = get_object_or_404(Task, pk=task_id)

            if task.approved and (action in ['approve', 'accept']):
                return Response({"detail": "Bu tapşırıq artıq təsdiqlənib"}, status=status.HTTP_400_BAD_REQUEST)

            if action == 'approve':
                task.approved = True
                task.status = "TODO"  
                task.save()
                return Response({"detail": "Tapşırıq uğurla təsdiqləndi."}, status=status.HTTP_200_OK)
             
            elif action == 'accept':
                task.approved = True
                task.status = "TODO"
                task.save()
                return Response({"detail": "Tapşırıq uğurla qəbul edildi."}, status=status.HTTP_200_OK)

            elif action == 'reject':
                title = task.title
                task.delete()
                return Response({"detail": f"'{title}' adlı tapşırıq  sistemdən silindi."}, status=status.HTTP_200_OK)
             
            elif action == 'reject_assignment':
                title = task.title
                task.delete()
                return Response({"detail": f"'{title}' adlı təyin edilmiş tapşırıq sistemdən silindi."}, status=status.HTTP_200_OK)
             
            else:
                return Response({"detail": "Naməlum əməliyyat."}, status=status.HTTP_400_BAD_REQUEST)

        except BadSignature:
            return Response({"detail": "Etibarsız və ya vaxtı keçmiş token."}, status=status.HTTP_400_BAD_REQUEST)
        except Task.DoesNotExist:
            return Response({"detail": "Tapşırıq tapılmadı. Artıq silinmiş ola bilər."}, status=status.HTTP_404_NOT_FOUND)