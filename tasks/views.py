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


# === YENİ YARDIMÇI FUNKSİYA (TƏKRARLANMANIN QARŞISINI ALMAQ ÜÇÜN) ===
def get_visible_tasks(user):
    """
    İstifadəçinin roluna görə görə biləcəyi bütün tapşırıqları qaytarır.
    Bu, bütün view-lar üçün tək mənbədir.
    """
    if  user.role == "admin":
        return Task.objects.all()

    subordinate_ids = user.get_subordinates().values_list('id', flat=True)
    query = Q(assignee=user) | Q(assignee__id__in=list(subordinate_ids))
    
    return Task.objects.filter(query).distinct()



class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskFilter 
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Artıq bütün məntiq mərkəzləşdirilmiş yardımçı funksiyadan gəlir."""
        return get_visible_tasks(self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]

        # 1. İstifadəçi özünə tapşırıq verirsə (təsdiqə gedir)
        if creator == assignee:
            superior = creator.get_superior()
            if superior:
                task = serializer.save(created_by=creator, approved=False, status="PENDING")
                send_task_notification_email(task, notification_type="approval_request")
            else:
                # Rəhbəri yoxdursa, tapşırıq avtomatik təsdiqlənir
                task = serializer.save(created_by=creator, approved=True, status="TODO")
            return

        # 2. İstifadəçi başqasına tapşırıq verirsə (icazə yoxlaması)
        subordinates = creator.get_subordinates()
        if not creator.is_staff and creator.role != 'admin' and assignee not in subordinates:
            raise PermissionDenied("Siz yalnız tabeliyinizdə olan işçilərə tapşırıq təyin edə bilərsiniz.")

        task = serializer.save(created_by=creator, approved=True, status="TODO")
        send_task_notification_email(task, notification_type="new_assignment")


class AssignableUserListView(generics.ListAPIView):
    """Tapşırıq təyin edilə bilən istifadəçilərin siyahısını qaytarır."""
    serializer_class = TaskUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Məntiq tamamilə get_subordinates metodundan gəlir. Sadə və dəqiq."""
        return self.request.user.get_subordinates()


class HomeStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Statistikalar üçün də mərkəzi funksiyadan istifadə edirik
        base_queryset = get_visible_tasks(request.user)

        today = timezone.now().date()
        
        # Rəhbərlər üçün statistika yalnız onların tabeçiliyində olanları əhatə edir
        stats_queryset = base_queryset.exclude(assignee=request.user) if request.user.role != 'employee' else base_queryset

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
        
        labels = [priority_map.get(p['priority'], p['priority']) for p in priority_stats]
        data = [p['count'] for p in priority_stats]

        return Response({'labels': labels, 'data': data})


class TaskVerificationView(views.APIView):
    # Bu view olduğu kimi qala bilər, çünki onun məntiqi fərqlidir.
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
        date = serializer.validated_data.get('date')
        instance = CalendarNote.objects.filter(user=self.request.user, date=date).first()
        if instance:
            self.perform_update(serializer)
        else:
            serializer.save(user=self.request.user)
            
    def perform_update(self, serializer):
        serializer.save(user=self.request.user)