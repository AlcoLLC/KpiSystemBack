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
        """
        İstifadəçinin roluna görə görə biləcəyi tapşırıqları iyerarxiyaya uyğun filterləyir.
        """
        user = self.request.user

        if user.is_staff and user.role == "admin":
            queryset = Task.objects.all()

        elif user.role == 'top_management':
            queryset = Task.objects.filter(
                Q(assignee=user) | 
                Q(assignee__role__in=['department_lead', 'manager', 'employee'])
            )

        elif user.role == 'department_lead':
            try:
                user_departments = Department.objects.filter(lead=user)
                if user_departments.exists():
                    subordinate_tasks = Q(
                        assignee__department__in=user_departments,
                        assignee__role__in=['manager', 'employee']
                    )
                    own_tasks = Q(assignee=user)
                    queryset = Task.objects.filter(subordinate_tasks | own_tasks)
                else:
                    queryset = Task.objects.filter(assignee=user)
            except Exception:
                queryset = Task.objects.filter(assignee=user)

        elif user.role == 'manager':
            if user.department:
                queryset = Task.objects.filter(
                    Q(assignee__department=user.department, assignee__role='employee') |
                    Q(assignee=user)
                )
            else:
                queryset = Task.objects.filter(assignee=user)

        elif user.role == 'employee':
            queryset = Task.objects.filter(assignee=user)
        
        else:
            queryset = Task.objects.none()

        return queryset.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]

        if creator == assignee:
            superior = creator.get_superior()
            if superior:
                task = serializer.save(created_by=creator, approved=False, status="PENDING")
                send_task_notification_email(task, notification_type="approval_request")
            else:
                task = serializer.save(created_by=creator, approved=True, status="TODO")
            return

        if creator.role == "employee":
            raise PermissionDenied("Employees cannot assign tasks to others.")
        
        allowed_assignments = {
            "top_management": ["department_lead", "manager", "employee"],
            "department_lead": ["manager", "employee"],
            "manager": ["employee"],
            "admin": ["top_management", "department_lead", "manager", "employee"]
        }

        allowed_roles = allowed_assignments.get(creator.role, [])
        if assignee.role not in allowed_roles:
            raise PermissionDenied(f"{creator.get_role_display()} can only assign tasks to specific roles.")

        if creator.role in ["admin", "top_management"]:
            task = serializer.save(created_by=creator, approved=True, status="TODO")
        else:
            task = serializer.save(created_by=creator, approved=False, status="PENDING")
        
        send_task_notification_email(task, notification_type="new_assignment")


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
