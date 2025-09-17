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

    def _get_role_hierarchy_index(self, role):
        """Get the index of a role in the hierarchy (lower index = higher role)"""
        role_hierarchy = ["admin", "top_management", "department_lead", "manager", "employee"]
        try:
            return role_hierarchy.index(role)
        except ValueError:
            return -1

    def _can_assign_to_role(self, creator_role, assignee_role):
        """Check if creator role can assign tasks to assignee role"""
        creator_index = self._get_role_hierarchy_index(creator_role)
        assignee_index = self._get_role_hierarchy_index(assignee_role)
        
        # Invalid roles
        if creator_index == -1 or assignee_index == -1:
            return False
            
        # Higher roles (lower index) can assign to lower roles (higher index)
        return creator_index < assignee_index

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]

        # Self-assignment case
        if creator == assignee:
            superior = creator.get_superior()
            if superior:
                task = serializer.save(created_by=creator, approved=False)
                send_task_notification_email(task, notification_type='approval_request')
            else:
                serializer.save(created_by=creator, approved=True)
            return

        # Check if creator can assign to assignee based on role hierarchy
        if not self._can_assign_to_role(creator.role, assignee.role):
            role_permissions = {
                "employee": "Employees cannot assign tasks to other users.",
                "manager": "Managers can only assign tasks to employees.",
                "department_lead": "Department Leads can assign tasks to managers and employees.",
                "top_management": "Top Management can assign tasks to department leads, managers, and employees.",
                "admin": "Admins can assign tasks to all users."
            }
            error_message = role_permissions.get(creator.role, "You don't have permission to assign tasks to this user.")
            raise PermissionDenied(error_message)

        # Special handling for employee assignments - check department permissions
        if assignee.role == "employee":
            if not assignee.department:
                raise ValidationError("The assigned employee does not belong to any department.")
            
            # For non-admin/top_management users, check department permissions
            if creator.role not in ["admin", "top_management"]:
                department = assignee.department
                designated_creator = department.manager or department.lead
                if not designated_creator:
                    raise ValidationError(f"The department '{department.name}' has no assigned Manager or Lead.")
                if creator != designated_creator:
                    raise PermissionDenied(f"You are not the designated manager or lead for this employee's department.")

        # Determine notification type and approval status
        notification_type = 'new_assignment'
        approved = False

        # Tasks assigned to employees are typically approved immediately by their direct supervisors
        if assignee.role == "employee" and creator.role in ["manager", "department_lead", "top_management", "admin"]:
            approved = False  # Still needs approval from assignee's supervisor if self-created
            notification_type = 'new_assignment'
        # Tasks assigned to higher roles need acceptance
        elif assignee.role in ["manager", "department_lead", "top_management"]:
            approved = False
            notification_type = 'assignment_acceptance_request'

        task = serializer.save(created_by=creator, approved=approved)
        send_task_notification_email(task, notification_type=notification_type)


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
                title = task.title
                task.delete()
                return Response({"detail": f"'{title}' adlı tapşırıq rədd edildi və sistemdən silindi."}, status=status.HTTP_200_OK)
            
            elif action == 'reject_assignment':
                title = task.title
                task.delete()
                return Response({"detail": f"'{title}' adlı təyin edilmiş tapşırıq rədd edildi və sistemdən silindi."}, status=status.HTTP_200_OK)
            
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

        # Staff and admin can assign to anyone
        if user.is_staff or user.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=user.pk)

        role_hierarchy = ["admin", "top_management", "department_lead", "manager", "employee"]

        try:
            user_index = role_hierarchy.index(user.role)
        except ValueError:
            return User.objects.none()

        # Get all roles that are lower in hierarchy (higher index)
        assignable_roles = role_hierarchy[user_index+1:]
        
        if not assignable_roles:
            return User.objects.none()

        # Base queryset for assignable users
        queryset = User.objects.filter(
            role__in=assignable_roles,
            is_active=True
        ).exclude(pk=user.pk)

        # For non-admin/top_management, apply department restrictions for employees
        if user.role not in ["admin", "top_management"]:
            if not user.department:
                return User.objects.none()
            
            # Can assign to employees in their department, and other roles regardless of department
            queryset = queryset.filter(
                Q(role="employee", department=user.department) |
                Q(role__in=[role for role in assignable_roles if role != "employee"])
            )

        return queryset.order_by("first_name", "last_name")