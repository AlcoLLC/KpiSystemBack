from rest_framework import serializers
from .models import Equipment, EquipmentVolume, DailyProduction, ProductionItem
from django.contrib.auth import get_user_model

class EquipmentVolumeSerializer(serializers.ModelSerializer):
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all())
    equipment_name = serializers.ReadOnlyField(source='equipment.name')

    class Meta:
        model = EquipmentVolume
        fields = ['id', 'equipment', 'equipment_name', 'volume']

class EquipmentSerializer(serializers.ModelSerializer):
    volumes = EquipmentVolumeSerializer(many=True, read_only=True)
    type_display = serializers.CharField(source='get_equipment_type_display', read_only=True)

    class Meta:
        model = Equipment
        fields = ['id', 'name', 'equipment_type', 'type_display', 'volumes']

        from rest_framework import serializers

User = get_user_model()

class UserShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'factory_role']

class ProductionItemSerializer(serializers.ModelSerializer):
    volume_name = serializers.ReadOnlyField(source='volume.volume')
    class Meta:
        model = ProductionItem
        fields = ['id', 'production', 'volume', 'production_hours', 'actual_count', 'target_norm', 'efficiency', 'volume_name']
        read_only_fields = ['production', 'efficiency']

class DailyProductionSerializer(serializers.ModelSerializer):
    items = ProductionItemSerializer(many=True)
    equipment_obj = serializers.ReadOnlyField(source='equipment_name')
    employees_obj = serializers.ReadOnlyField(source='employee_details')

    class Meta:
        model = DailyProduction
        fields = '__all__'

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        employees = validated_data.pop('employees', [])
        production = DailyProduction.objects.create(**validated_data)
        production.employees.set(employees)
        for item in items_data:
            ProductionItem.objects.create(production=production, **item)
        production.calculate_results()
        return production

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', [])
        employees = validated_data.pop('employees', None)
        
        instance.date = validated_data.get('date', instance.date)
        instance.shift = validated_data.get('shift', instance.shift)
        instance.equipment = validated_data.get('equipment', instance.equipment)
        instance.note = validated_data.get('note', instance.note)
        instance.save()

        if employees is not None:
            instance.employees.set(employees)

        instance.items.all().delete()
        for item in items_data:
            ProductionItem.objects.create(production=instance, **item)
        
        instance.calculate_results()
        return instance