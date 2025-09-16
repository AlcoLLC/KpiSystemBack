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
                send_task_notification_email(task, notification_type='approval_request')
            else:
                serializer.save(created_by=creator, approved=True)
            return

        if assignee.role == "employee":
            if not assignee.department:
                raise ValidationError("The assigned employee does not belong to any department.")
            department = assignee.department
            designated_creator = department.manager or department.lead
            if not designated_creator:
                raise ValidationError(f"The department '{department.name}' has no assigned Manager or Lead.")
            if creator != designated_creator:
                 raise PermissionDenied(f"You are not the designated manager or lead for this employee's department.")
            
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type='new_assignment')
            return

        elif assignee.role == "manager":
            if creator.role != "department_lead":
                raise PermissionDenied("Only Department Leads can assign tasks to Managers.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type='assignment_acceptance_request')
            return

        elif assignee.role == "department_lead":
            if creator.role != "top_management":
                raise PermissionDenied("Only Top Management can assign tasks to Department Leads.")
            task = serializer.save(created_by=creator, approved=False)
            send_task_notification_email(task, notification_type='assignment_acceptance_request')
            return
            
        elif assignee.role == "top_management":
            if creator.role != "department_lead":
                 raise PermissionDenied("Only Department Leads can create tasks for Top Management.")
        
        elif assignee.role == "admin":
            raise PermissionDenied("You cannot assign tasks to a user with the admin role.")

        task = serializer.save(created_by=creator, approved=False)
        send_task_notification_email(task, notification_type='new_assignment')


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
        """
        Kullanıcıların görev atayabileceği kişileri listeler.
        Kurallar:
        1. Admin/staff her zaman herkese görev atayabilir.
        2. Kullanıcılar yalnızca kendi departmanlarındaki kişilere görev atayabilir.
        3. Kullanıcılar yalnızca hiyerarşide kendilerinden daha alt roldeki kişilere görev atayabilir.
        """
        user = self.request.user

        # Kural 1: Admin veya staff ise, aktif olan herkesi (kendisi hariç) listeleyin.
        if user.is_staff or user.role == 'admin':
            return User.objects.filter(is_active=True).exclude(pk=user.pk).order_by('first_name', 'last_name')

        # Kullanıcının bir departmanı yoksa, kimseye görev atayamaz.
        if not user.department:
            return User.objects.none()

        # Rol hiyerarşisini tanımlayalım (daha yüksek sayı, daha yüksek rütbe)
        role_hierarchy = {
            "top_management": 4,
            "department_lead": 3,
            "manager": 2,
            "employee": 1,
        }

        # Mevcut kullanıcının rütbesini alalım.
        user_rank = role_hierarchy.get(user.role)

        # Eğer kullanıcının rütbesi tanımlı değilse veya en alttaysa (employee), kimseye atama yapamaz.
        if not user_rank:
            return User.objects.none()

        # Mevcut kullanıcının rütbesinden daha düşük rütbeye sahip rolleri bulalım.
        lower_roles = [role for role, rank in role_hierarchy.items() if rank < user_rank]

        if not lower_roles:
            return User.objects.none() # Atanacak daha alt bir rol yoksa boş liste döndür.

        # Kural 2 & 3: Kullanıcının departmanındaki ve daha alt roldeki aktif kullanıcıları filtreleyelim.
        assignable_users = User.objects.filter(
            department=user.department,
            role__in=lower_roles,
            is_active=True
        ).exclude(pk=user.pk).distinct().order_by('first_name', 'last_name')

        return assignable_users