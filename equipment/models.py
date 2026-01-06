from django.db import models
from django.conf import settings

class Equipment(models.Model):
    TYPE_CHOICES = [
        ('bidon', 'Bidon'),
        ('dolum', 'Dolum'),
    ]

    name = models.CharField(max_length=255, verbose_name="Avadanlıq adı")
    equipment_type = models.CharField(
        max_length=10, 
        choices=TYPE_CHOICES, 
        default='bidon',
        verbose_name="Seçim növü"
    )

    def __str__(self):
        return f"{self.name} ({self.get_equipment_type_display()})"


class EquipmentVolume(models.Model):
    equipment = models.ForeignKey(Equipment, related_name='volumes', on_delete=models.CASCADE)
    volume = models.CharField(max_length=50, verbose_name="Litraj")
    max_norm_8h = models.IntegerField(default=0, verbose_name="Maksimum istehsal norması (8 saat üçün)")

    def __str__(self):
        return f"{self.equipment.name} - {self.volume}"


class DailyProduction(models.Model):
    SHIFT_CHOICES = [(1, '1-ci smen'), (2, '2-ci smen'), (3, '3-cü smen')]
    
    date = models.DateField(verbose_name="Tarix")
    shift = models.IntegerField(choices=SHIFT_CHOICES, verbose_name="Smen")
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, verbose_name="Avadanlıq")
    employees = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='productions', 
        verbose_name="İşçilər"
    )
    note = models.TextField(blank=True, null=True, verbose_name="Qeyd")
    final_efficiency = models.FloatField(default=0.0, verbose_name="Yekun səmərəlilik %")

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "Gündəlik İstehsal"
        verbose_name_plural = "Gündəlik İstehsallar"

    def calculate_results(self):
        items = self.items.all()
        if not items.exists():
            self.final_efficiency = 0.0
        else:
            total_hours = sum(item.production_hours for item in items)
            if total_hours > 0:
                weighted_sum = sum(
                    (item.efficiency * item.production_hours) 
                    for item in items
                )
                self.final_efficiency = round(weighted_sum / total_hours, 2)
            else:
                self.final_efficiency = 0.0
        self.save()

    def __str__(self):
        return f"{self.date} - {self.equipment.name} - Smen {self.shift}"
    
    @property
    def equipment_name(self):
        return self.equipment.name

    @property
    def employee_details(self):
        return [
            {
                "id": emp.id, 
                "full_name": f"{emp.first_name} {emp.last_name}",
                "factory_role": emp.factory_role
            } 
            for emp in self.employees.all()
        ]


class ProductionItem(models.Model):
    production = models.ForeignKey(
        DailyProduction, 
        related_name='items', 
        on_delete=models.CASCADE
    )
    volume = models.ForeignKey(
        EquipmentVolume, 
        on_delete=models.CASCADE, 
        verbose_name="Tiraj"
    )
    production_hours = models.FloatField(default=0, verbose_name="Dolum saatı")
    actual_count = models.IntegerField(default=0, verbose_name="Hazır dolum sayı")
    target_norm = models.IntegerField(default=0, verbose_name="İstehsal norması")
    efficiency = models.FloatField(default=0.0, verbose_name="Səmərəlilik %")

    class Meta:
        verbose_name = "İstehsal Elementi"
        verbose_name_plural = "İstehsal Elementləri"

    def save(self, *args, **kwargs):
        if self.target_norm > 0:
            self.efficiency = round((self.actual_count / self.target_norm) * 100, 2)
        else:
            self.efficiency = 0.0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.production} - {self.volume.volume}"