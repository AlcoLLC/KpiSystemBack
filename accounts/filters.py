from django_filters import rest_framework as filters
from .models import User
from django.db.models import Q

class UserFilter(filters.FilterSet):
    search = filters.CharFilter(method='filter_by_search')

    class Meta:
        model = User
        fields = ['role', 'department', 'position', 'search']

    def filter_by_search(self, queryset, name, value):
        return queryset.filter(
            Q(first_name__icontains=value) | 
            Q(last_name__icontains=value) | 
            Q(email__icontains=value)
        )