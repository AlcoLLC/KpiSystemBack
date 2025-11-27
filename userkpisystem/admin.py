from django.contrib import admin
from .models import UserEvaluation

@admin.register(UserEvaluation)
class UserEvaluationAdmin(admin.ModelAdmin):
    # YENİLƏNDİ: 'evaluation_type' əlavə edildi
    list_display = (
        'evaluatee', 
        'get_evaluatee_department',
        'evaluator', 
        'evaluation_type', # Yeni
        'score', 
        'evaluation_date',
        'created_at',
        'updated_at',
    )
    
    # YENİLƏNDİ: 'evaluation_type' əlavə edildi
    list_filter = (
        'evaluation_date',
        'evaluation_type', # Yeni
        'score',
        'evaluatee__department',
        'evaluator',
    )
    
    search_fields = (
        'evaluatee__first_name', 
        'evaluatee__last_name', 
        'evaluatee__username',
        'evaluator__first_name', 
        'evaluator__last_name', 
        'evaluator__username',
        'comment',
    )
    
    # YENİLƏNDİ: 'evaluation_type' əlavə edildi
    fieldsets = (
        ('Əsas Dəyərləndirmə Məlumatları', {
            'fields': ('evaluator', 'evaluatee', 'evaluation_type', 'score', 'comment', 'evaluation_date')
        }),
        ('Dəyişiklik Tarixçəsi (Avtomatik)', {
            'fields': ('previous_score', 'updated_by', 'history'),
            'classes': ('collapse',), 
        }),
        ('Sistem Məlumatları (Avtomatik)', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = (
        'previous_score',
        'updated_by',
        'history',
        'created_at',
        'updated_at',
    )
    
    ordering = ('-evaluation_date',)

    @admin.display(description='Departament', ordering='evaluatee__department')
    def get_evaluatee_department(self, obj):
        if obj.evaluatee and obj.evaluatee.department:
            return obj.evaluatee.department.name
        return "Təyin edilməyib"