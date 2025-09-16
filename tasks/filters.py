from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Task

class TaskFilter(filters.FilterSet):
    start_date_after = filters.DateFilter(field_name='start_date', lookup_expr='gte')
    due_date_before = filters.DateFilter(field_name='due_date', lookup_expr='lte')

    department = filters.NumberFilter(field_name='assignee__department__id')

    search = filters.CharFilter(method='filter_by_search', label="Search in title and description")

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
        ]
    
    def filter_by_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )