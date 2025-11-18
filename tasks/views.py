from django.db.models import Q, Count
from django.db.models.functions import TruncMonth
from django.core.signing import Signer, BadSignature
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, permissions, views, status, generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from accounts.models import User
from .models import Task, CalendarNote
from .serializers import TaskSerializer, TaskUserSerializer, CalendarNoteSerializer
from .utils import send_task_notification_email
from .filters import TaskFilter
from .pagination import CustomPageNumberPagination

from reports.utils import create_log_entry
from reports.models import ActivityLog


def get_visible_tasks(user):
    if user.role == "admin":
        return Task.objects.all()

    subordinate_ids = user.get_subordinates().values_list('id', flat=True)
    query = Q(assignee=user) | Q(assignee_id__in=list(subordinate_ids))

    if user.role == "ceo":
        top_management_subordinates = user.get_kpi_subordinates().filter(
            role='top_management'
        ).values_list('id', flat=True)
        
        if top_management_subordinates:
             query |= Q(assignee_id__in=list(top_management_subordinates))
             
        query |= Q(assignee=user)
    
    return Task.objects.filter(query).distinct()


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskFilter 
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return get_visible_tasks(self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]

        if creator != assignee and creator.role != 'admin':
            subordinates = creator.get_subordinates()
            if assignee not in subordinates:
                raise PermissionDenied("Siz yalnız tabeliyinizdə olan işçilərə tapşırıq təyin edə bilərsiniz.")

        is_approved = True
        task_status = "TODO"
        needs_approval_email = False

        if creator.role == 'top_management':
            superior = creator.get_superior()
            if superior and superior.role == 'ceo':
                is_approved = False
                task_status = "PENDING"
                needs_approval_email = True
        
        elif creator == assignee:
            superior = creator.get_superior()
            if superior: 
                is_approved = False
                task_status = "PENDING"
                needs_approval_email = True

        task = serializer.save(
            created_by=creator, 
            approved=is_approved, 
            status=task_status
        )

        create_log_entry(
            actor=creator,
            action_type=ActivityLog.ActionTypes.TASK_CREATED,
            target_user=assignee,
            target_task=task,
            details={'task_title': task.title}
        )

        if needs_approval_email:
            send_task_notification_email(task, notification_type="approval_request")
        elif creator != assignee:
            send_task_notification_email(task, notification_type="new_assignment")

    def perform_update(self, serializer):
        original_task = self.get_object()
        original_status = original_task.status
        
        updated_task = serializer.save()
        
        if original_status != updated_task.status:
            create_log_entry(
                actor=self.request.user,
                action_type=ActivityLog.ActionTypes.TASK_STATUS_CHANGED,
                target_user=updated_task.assignee,
                target_task=updated_task,
                details={
                    'task_title': updated_task.title,
                    'old_status': original_status,
                    'new_status': updated_task.status
                }
            )


class AssignableUserListView(generics.ListAPIView):
    serializer_class = TaskUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return self.request.user.get_subordinates()


class HomeStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        base_queryset = get_visible_tasks(request.user)
        today = timezone.now().date()
        
        stats_queryset = base_queryset
        if request.user.role not in ['admin', 'employee', 'ceo']:
             stats_queryset = base_queryset.exclude(assignee=request.user)

        data = {
            "pending": stats_queryset.filter(status='PENDING').count(),
            "in_progress": stats_queryset.filter(status='IN_PROGRESS').count(),
            "cancelled": stats_queryset.filter(status='CANCELLED').count(),
            "overdue": stats_queryset.filter(
                due_date__lt=today, 
                status__in=['PENDING', 'TODO', 'IN_PROGRESS']
            ).count(),
        }
        return Response(data, status=status.HTTP_200_OK)


class MonthlyTaskStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        base_queryset = get_visible_tasks(request.user)
        six_months_ago = timezone.now() - timedelta(days=180)

        completed_tasks_stats = base_queryset.filter(
            status='DONE',
            created_at__gte=six_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(count=Count('id')).order_by('month')
        
        stats = [
            {"month": item['month'].strftime('%Y-%m'), "count": item['count']} 
            for item in completed_tasks_stats
        ]
        return Response(stats)
        

class PriorityTaskStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        base_queryset = get_visible_tasks(request.user)
        priority_stats = base_queryset.values('priority').annotate(count=Count('id')).order_by('priority')
        priority_map = dict(Task.PRIORITY_CHOICES)
        
        labels = [str(priority_map.get(p['priority'], p['priority'])) for p in priority_stats]
        data = [p['count'] for p in priority_stats]

        return Response({'labels': labels, 'data': data})


class TaskVerificationView(views.APIView):
    permission_classes = [permissions.AllowAny] 

    def get(self, request, token, *args, **kwargs):
        signer = Signer()
        try:
            data = signer.unsign_object(token)
            task_id = data['task_id']
            action = data['action']
            task = get_object_or_404(Task, pk=task_id)

            if task.status != "PENDING" and action in ['approve', 'reject']:
                return Response({"detail": "Bu tapşırıq artıq cavablandırılıb."}, status=status.HTTP_400_BAD_REQUEST)

            if action == 'approve':
                task.approved = True
                task.status = "TODO"
                task.save()
                
                superior = task.assignee.get_superior()
                if superior:
                    create_log_entry(
                        actor=superior,
                        action_type=ActivityLog.ActionTypes.TASK_APPROVED,
                        target_user=task.assignee,
                        target_task=task,
                        details={'task_title': task.title}
                    )
                return Response({"detail": "Tapşırıq uğurla təsdiqləndi."}, status=status.HTTP_200_OK)
            
            elif action == 'reject':
                task.status = "CANCELLED"
                task.save()
                return Response({"detail": f"'{task.title}' adlı tapşırıq rədd edildi."}, status=status.HTTP_200_OK)
            
            else:
                return Response({"detail": "Naməlum əməliyyat."}, status=status.HTTP_400_BAD_REQUEST)

        except BadSignature:
            return Response({"detail": "Etibarsız və ya vaxtı keçmiş link."}, status=status.HTTP_400_BAD_REQUEST)
        except Task.DoesNotExist:
            return Response({"detail": "Tapşırıq tapılmadı."}, status=status.HTTP_404_NOT_FOUND)


class CalendarNoteViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        queryset = CalendarNote.objects.filter(user=self.request.user)
        
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
            
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)