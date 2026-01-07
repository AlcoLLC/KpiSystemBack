from django_filters import rest_framework as filters
from .models import Equipment, EquipmentVolume, DailyProduction
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

class EquipmentFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    equipment_type = filters.CharFilter(lookup_expr='exact')

    class Meta:
        model = Equipment
        fields = ['name', 'equipment_type']


class EquipmentVolumeFilter(filters.FilterSet):
    volume = filters.CharFilter(lookup_expr='icontains')
    equipment_name = filters.CharFilter(field_name='equipment__name', lookup_expr='icontains')
    equipment_id = filters.NumberFilter(field_name='equipment__id', lookup_expr='exact')
    equipment = filters.ModelChoiceFilter(queryset=Equipment.objects.all())

    class Meta:
        model = EquipmentVolume
        fields = ['volume', 'equipment_name', 'equipment_id', 'equipment']


class DailyProductionFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="date", lookup_expr='gte')
    end_date = filters.DateFilter(field_name="date", lookup_expr='lte')
    type = filters.CharFilter(field_name="equipment__equipment_type")
    equipment = filters.NumberFilter(field_name="equipment__id")

    class Meta:
        model = DailyProduction
        fields = ['date', 'equipment', 'shift']

    @property
    def qs(self):
        parent = super().qs
        request = self.request
        
        if not request or not hasattr(request, 'user'):
            return parent.none()
        
        user = request.user
        
        if user.role in ['admin', 'ceo', 'top_management']:
            return parent
        
        if user.factory_role == 'admin':
            return parent
        
        if not user.factory_role or not user.factory_type:
            return parent.none()
        
        parent = parent.filter(equipment__equipment_type=user.factory_type)
        
        if user.factory_role == 'top_management':
            return parent
        
        elif user.factory_role == 'deputy_director':
            return parent.filter(
                models.Q(employees__factory_role__in=['department_lead', 'employee']) | 
                models.Q(employees=user)
            ).distinct()
        
        elif user.factory_role == 'department_lead':
            return parent.filter(
                models.Q(employees__factory_role='employee') | 
                models.Q(employees=user)
            ).distinct()
        
        elif user.factory_role == 'employee':
            return parent.filter(employees=user).distinct()
        
        return parent.none()