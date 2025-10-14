from django_filters import rest_framework as filters
from django.db.models import Q, F
from django.utils import timezone
from .models import Task

STATUS_CHOICES = Task.STATUS_CHOICES 

class TaskFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(
        choices=STATUS_CHOICES,
    )
    start_date_after = filters.DateFilter(field_name='start_date', lookup_expr='gte')
    due_date_before = filters.DateFilter(field_name='due_date', lookup_expr='lte')
    department = filters.NumberFilter(field_name='assignee__department__id')
    search = filters.CharFilter(method='filter_by_search', label="Search in title and description")
    exclude_assignee = filters.NumberFilter(method='filter_exclude_assignee', label="Exclude assignee by ID")
    overdue = filters.BooleanFilter(method='filter_overdue', label='Gecikmiş tapşırıqlar')


    class Meta:
        model = Task
        fields = [
            'status',
            'priority',
            'assignee',
            'department',
            'start_date_after',
            'due_date_before',
            'search',
            'exclude_assignee',
            'overdue'
        ]
    
    def filter_by_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
    
    def filter_exclude_assignee(self, queryset, name, value):
        try:
            return queryset.exclude(assignee__id=int(value))
        except (ValueError, TypeError):
            return queryset
        
    def filter_overdue(self, queryset, name, value):
        if value:
            today = timezone.now().date()
            start_of_month = today.replace(day=1)
            
            overdue_not_completed = Q(due_date__lt=today, status__in=['PENDING', 'TODO', 'IN_PROGRESS'])
            late_completed_this_month = Q(completed_at__gte=start_of_month, completed_at__date__gt=F('due_date'))
            
            return queryset.filter(overdue_not_completed | late_completed_this_month).distinct()
        return queryset