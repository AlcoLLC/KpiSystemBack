from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Task

class TaskFilter(filters.FilterSet):
    start_date_after = filters.DateFilter(field_name='start_date', lookup_expr='gte')
    due_date_before = filters.DateFilter(field_name='due_date', lookup_expr='lte')
    department = filters.NumberFilter(field_name='assignee__department__id')
    search = filters.CharFilter(method='filter_by_search', label="Search in title and description")
    exclude_assignee = filters.NumberFilter(method='filter_exclude_assignee', label="Exclude assignee by ID")

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
        ]
    
    def filter_by_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
    
    def filter_exclude_assignee(self, queryset, name, value):
        """
        Verilmiş ID-yə sahib olan icraçının tapşırıqlarını nəticələrdən çıxarır.
        """
        try:
            return queryset.exclude(assignee__id=int(value))
        except (ValueError, TypeError):
            return queryset