from django_filters import rest_framework as filters
from .models import Equipment, EquipmentVolume, DailyProduction

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

    class Meta:
        model = EquipmentVolume
        fields = ['volume', 'equipment_name', 'equipment_id']

class DailyProductionFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="date", lookup_expr='gte')
    end_date = filters.DateFilter(field_name="date", lookup_expr='lte')
    type = filters.CharFilter(field_name="equipment__equipment_type")
    equipment = filters.NumberFilter(field_name="equipment__id")

    class Meta:
        model = DailyProduction
        fields = ['date', 'equipment', 'shift']