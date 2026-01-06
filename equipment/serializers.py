from rest_framework import serializers
from .models import Equipment, EquipmentVolume, DailyProduction, ProductionItem
from django.contrib.auth import get_user_model

User = get_user_model()


class EquipmentVolumeSerializer(serializers.ModelSerializer):
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all())
    equipment_name = serializers.ReadOnlyField(source='equipment.name')

    class Meta:
        model = EquipmentVolume
        fields = ['id', 'equipment', 'equipment_name', 'volume', 'max_norm_8h']


class EquipmentSerializer(serializers.ModelSerializer):
    volumes = EquipmentVolumeSerializer(many=True, read_only=True)
    type_display = serializers.CharField(source='get_equipment_type_display', read_only=True)

    class Meta:
        model = Equipment
        fields = ['id', 'name', 'equipment_type', 'type_display', 'volumes']


class UserShortSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'factory_role', 'full_name']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class ProductionItemSerializer(serializers.ModelSerializer):
    volume_name = serializers.ReadOnlyField(source='volume.volume')
    
    class Meta:
        model = ProductionItem
        fields = ['id', 'production', 'volume', 'production_hours', 'actual_count', 
                  'target_norm', 'efficiency', 'volume_name']
        read_only_fields = ['production', 'efficiency']


class DailyProductionSerializer(serializers.ModelSerializer):
    items = ProductionItemSerializer(many=True)
    equipment_obj = serializers.CharField(source='equipment_name', read_only=True)
    employees_obj = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = DailyProduction
        fields = ['id', 'date', 'shift', 'equipment', 'equipment_obj', 'employees', 
                  'employees_obj', 'note', 'final_efficiency', 'items']
    
    def get_employees_obj(self, obj):
        return [
            {
                "id": emp.id, 
                "full_name": f"{emp.first_name} {emp.last_name}",
                "factory_role": emp.factory_role
            } 
            for emp in obj.employees.all()
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        employees = validated_data.pop('employees', [])
        
        production = DailyProduction.objects.create(**validated_data)
        production.employees.set(employees)
        
        for item_data in items_data:
            ProductionItem.objects.create(production=production, **item_data)
        
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
        for item_data in items_data:
            ProductionItem.objects.create(production=instance, **item_data)
        
        instance.calculate_results()
        return instance