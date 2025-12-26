from django.contrib import admin
from .models import Equipment, EquipmentVolume, DailyProduction, ProductionItem

class EquipmentVolumeInline(admin.TabularInline):
    model = EquipmentVolume
    extra = 1

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'equipment_type')
    inlines = [EquipmentVolumeInline]

class ProductionItemInline(admin.TabularInline):
    model = ProductionItem
    extra = 1

@admin.register(DailyProduction)
class DailyProductionAdmin(admin.ModelAdmin):
    list_display = ('date', 'equipment', 'shift', 'final_efficiency')
    filter_horizontal = ('employees',)
    inlines = [ProductionItemInline]
    
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.calculate_results()