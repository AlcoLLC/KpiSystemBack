from django.db.models import Q
from django.core.signing import Signer, BadSignature
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, views, status, generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from accounts.models import User, Department

from .models import Task
from .serializers import TaskSerializer, TaskUserSerializer
from .utils import send_task_notification_email
from django_filters.rest_framework import DjangoFilterBackend
from .filters import TaskFilter
from .pagination import CustomPageNumberPagination


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskFilter 
    pagination_class = CustomPageNumberPagination

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

        if creator == assignee:
            superior = creator.get_superior()
            if superior:
                task = serializer.save(created_by=creator, approved=False)
                send_task_notification_email(task, notification_type="approval_request")
            else:
                task = serializer.save(created_by=creator, approved=True)
            return

        if creator.role == "admin":
            if assignee.role == "admin":
                raise PermissionDenied("You cannot assign tasks to another admin.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type="new_assignment")
            return

        if creator.role == "top_management":
            if assignee.role not in ["department_lead", "manager", "employee"]:
                raise PermissionDenied("Top Management can only assign tasks to Department Leads, Managers, or Employees.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type="new_assignment")
            return

        if creator.role == "department_lead":
            if assignee.role not in ["manager", "employee"]:
                raise PermissionDenied("Department Leads can only assign tasks to Managers or Employees.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type="new_assignment")
            return

        if creator.role == "manager":
            if assignee.role != "employee":
                raise PermissionDenied("Managers can only assign tasks to Employees.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type="new_assignment")
            return

        if creator.role == "employee":
            raise PermissionDenied("Employees cannot assign tasks to others.")

        raise PermissionDenied("You are not allowed to assign this task.")


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
                return Response({"detail": "Bu tapşırıq artıq təsdiqlənib/qəbul edilib."}, status=status.HTTP_400_BAD_REQUEST)

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
                task.status = "CANCELLED"
                task.save()
                return Response({"detail": f"'{task.title}' adlı tapşırıq rədd edildi və statusu 'Ləğv edilib' olaraq dəyişdirildi."}, status=status.HTTP_200_OK)
            
            elif action == 'reject_assignment':
                task.status = "CANCELLED"
                task.save()
                return Response({"detail": f"'{task.title}' adlı təyin edilmiş tapşırıq rədd edildi və statusu 'Ləğv edilib' olaraq dəyişdirildi."}, status=status.HTTP_200_OK)
            
            else:
                return Response({"detail": "Naməlum əməliyyat."}, status=status.HTTP_400_BAD_REQUEST)

        except BadSignature:
            return Response({"detail": "Etibarsız və ya vaxtı keçmiş token."}, status=status.HTTP_400_BAD_REQUEST)
        except Task.DoesNotExist:
            return Response({"detail": "Tapşırıq tapılmadı. Artıq silinmiş ola bilər."}, status=status.HTTP_404_NOT_FOUND)

class AssignableUserListView(generics.ListAPIView):
    serializer_class = TaskUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user

        if user.is_staff and user.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=user.pk)

        if not user.department:
            return User.objects.none()

        role_hierarchy = ["admin", "top_management", "department_lead", "manager", "employee"]

        try:
            user_index = role_hierarchy.index(user.role)
        except ValueError:
            return User.objects.none()

        lower_roles = role_hierarchy[user_index+1:]

        return User.objects.filter(
            department=user.department,
            role__in=lower_roles,
            is_active=True
        ).exclude(pk=user.pk).order_by("first_name", "last_name")
