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


# Rolları və onların iyerarxik səviyyələrini müəyyən edən lüğət
# Daha yüksək rəqəm daha yüksək səlahiyyət deməkdir.
ROLE_HIERARCHY = {
    "admin": 5,
    "top_management": 4,
    "department_lead": 3,
    "manager": 2,
    "employee": 1,
}


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

        # 1. İstifadəçi özünə tapşırıq təyin edərsə (dəyişməyib)
        if creator == assignee:
            superior = creator.get_superior()
            if superior:
                task = serializer.save(created_by=creator, approved=False)
                send_task_notification_email(task, notification_type='approval_request')
            else:
                serializer.save(created_by=creator, approved=True, status="TODO")
            return

        # 2. 'admin' roluna tapşırıq təyin etməyi qadağan et
        if assignee.role == "admin":
            raise PermissionDenied("Siz 'admin' roluna sahib istifadəçiyə tapşırıq təyin edə bilməzsiniz.")

        # 3. İyerarxiya səviyyələrini yoxla
        creator_level = ROLE_HIERARCHY.get(creator.role, 0)
        assignee_level = ROLE_HIERARCHY.get(assignee.role, 0)

        # 4. Əsas icazə yoxlaması: Tapşırıq verənin səviyyəsi təyin olunanın səviyyəsindən yüksək olmalıdır
        if creator_level > assignee_level:
            # Departament məhdudiyyəti (köhnə məntiqdən fərqli olaraq daha çevikdir)
            # Yalnız menecer və departament rəhbəri öz departamentləri daxilində tapşırıq verə bilər
            if creator.role in ["manager", "department_lead"]:
                if not creator.department:
                     raise ValidationError("Siz heç bir departamentə aid deyilsiniz.")
                if creator.department != assignee.department:
                    raise PermissionDenied("Siz yalnız öz departamentinizdəki işçilərə tapşırıq verə bilərsiniz.")

            task = serializer.save(created_by=creator, approved=False)
            
            # Bildiriş növünü təyin et: Manager və Lead-lər tapşırığı qəbul etməlidir
            if assignee.role in ["manager", "department_lead"]:
                send_task_notification_email(task, notification_type='assignment_acceptance_request')
            else:
                send_task_notification_email(task, notification_type='new_assignment')
        else:
            # İcazə yoxdursa
            raise PermissionDenied("Bu istifadəçiyə tapşırıq təyin etmək üçün səlahiyyətiniz yoxdur.")

class TaskVerificationView(views.APIView):
    # Bu hissədə dəyişiklik edilməyib
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

        user_level = ROLE_HIERARCHY.get(user.role, 0)
        
        # İstifadəçinin rolu iyerarxiyada yoxdursa, boş siyahı qaytar
        if user_level == 0:
            return User.objects.none()

        # İstifadəçinin səviyyəsindən daha aşağı səviyyədə olan bütün rolları tap
        assignable_roles = [role for role, level in ROLE_HIERARCHY.items() if level < user_level]

        if not assignable_roles:
            return User.objects.none()

        # Başlanğıc queryset: aktiv və daha aşağı rolda olan istifadəçilər
        queryset = User.objects.filter(
            role__in=assignable_roles,
            is_active=True
        ).exclude(pk=user.pk)

        # Əgər tapşırıq verən manager və ya lead-dirsə, yalnız öz departamentindəki işçiləri göstər
        if user.role in ["manager", "department_lead"]:
            if not user.department:
                return User.objects.none()
            queryset = queryset.filter(department=user.department)

        return queryset.order_by("first_name", "last_name")