# logs/filters.py

import django_filters
from django.contrib.auth import get_user_model
from .models import ActivityLog

User = get_user_model()

class ActivityLogFilter(django_filters.FilterSet):
    actor = django_filters.ModelChoiceFilter(
        queryset=User.objects.all(),
        field_name='actor', 
        to_field_name='id'
    )
    
    action_type = django_filters.ChoiceFilter(choices=ActivityLog.ActionTypes.choices)
    start_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='lte')

    class Meta:
        model = ActivityLog
        fields = ['actor', 'action_type', 'start_date', 'end_date']