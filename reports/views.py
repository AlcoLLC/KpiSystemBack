# reports/views.py

from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import ActivityLog
from .serializers import ActivityLogSerializer
from tasks.pagination import CustomPageNumberPagination # Mövcud pagination istifadə edirik

class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Fəaliyyət tarixçəsini göstərmək üçün ViewSet.
    İstifadəçilər yalnız özlərinə və tabeliyində olanlara aid fəaliyyətləri görə bilər.
    """
    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            return ActivityLog.objects.all().select_related('actor', 'target_user', 'target_task')

        # İstifadəçinin tabeliyində olanların ID-lərini alırıq
        subordinate_ids = user.get_subordinates().values_list('id', flat=True)
        
        # Görünə bilən istifadəçi ID-ləri (özü + tabeliyində olanlar)
        visible_user_ids = list(subordinate_ids) + [user.id]

        # Fəaliyyəti icra edən (actor) və ya fəaliyyətin hədəfi olan (target_user)
        # şəxslər görünə bilən istifadəçilər siyahısında olmalıdır.
        query = Q(actor_id__in=visible_user_ids) | Q(target_user_id__in=visible_user_ids)
        
        return ActivityLog.objects.filter(query).distinct().select_related('actor', 'target_user', 'target_task')