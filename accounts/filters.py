from django_filters import rest_framework as filters
from .models import User
from django.db.models import Q

class UserFilter(filters.FilterSet):
    search = filters.CharFilter(method='filter_by_search')
    factory_type = filters.ChoiceFilter(choices=User.FACTORY_TYPES)
    factory_role = filters.ChoiceFilter(choices=User.FACTORY_ROLE_CHOICES)

    class Meta:
        model = User
        fields = ['role', 'department', 'position', 'factory_type', 'factory_role', 'search']

    def filter_by_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(first_name__icontains=value) | 
            Q(last_name__icontains=value) | 
            Q(email__icontains=value) |
            Q(username__icontains=value)
        )