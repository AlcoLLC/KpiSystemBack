import django_filters
from django.contrib.auth import get_user_model
from .models import ActivityLog
from datetime import timedelta

User = get_user_model()

class ActivityLogFilter(django_filters.FilterSet):
    actor = django_filters.ModelChoiceFilter(
        queryset=User.objects.all(),
        field_name='actor',
        to_field_name='id'
    )
    
    action_type = django_filters.ChoiceFilter(choices=ActivityLog.ActionTypes.choices)
    start_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='gte')
    
    end_date = django_filters.DateFilter(method='filter_end_date_inclusive')

    class Meta:
        model = ActivityLog
        fields = ['actor', 'action_type', 'start_date', 'end_date']

    def filter_end_date_inclusive(self, queryset, name, value):
        end_day = value + timedelta(days=1)
        return queryset.filter(timestamp__lt=end_day)