# performance/serializers.py

from rest_framework import serializers
from .models import UserEvaluation
from accounts.models import User
from django.utils import timezone

class UserEvaluationSerializer(serializers.ModelSerializer):
    evaluatee_id = serializers.IntegerField(write_only=True)
    
    # Oxumaq üçün detallı məlumatlar
    evaluator = serializers.StringRelatedField(read_only=True)
    evaluatee = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = UserEvaluation
        fields = [
            'id', 'evaluator', 'evaluatee', 'evaluatee_id', 'score',
            'comment', 'evaluation_date', 'previous_score', 'updated_by',
            'history', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'evaluator', 'previous_score', 'updated_by', 
            'history', 'created_at', 'updated_at'
        ]

    def validate_evaluation_date(self, value):
        # Dəyərləndirmə tarixi gələcəkdə ola bilməz
        if value > timezone.now().date():
            raise serializers.ValidationError("Dəyərləndirmə tarixi gələcəkdə ola bilməz.")
        # Ayın yalnız ilk gününü saxlayaq ki, unikal yoxlama düzgün işləsin
        return value.replace(day=1)

    def validate(self, data):
        request = self.context.get('request')
        evaluator = request.user
        
        try:
            evaluatee = User.objects.get(id=data['evaluatee_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belə bir istifadəçi tapılmadı.'})

        # --- İcazə Yoxlaması (Create/Update üçün) ---
        direct_superior = evaluatee.get_direct_superior()
        is_admin = evaluator.is_staff or evaluator.role == 'admin'

        if not is_admin and direct_superior != evaluator:
            raise serializers.ValidationError(
                "Yalnız işçinin birbaşa rəhbəri və ya Admin dəyərləndirmə edə bilər."
            )

        # --- Unikal Dəyərləndirmə Yoxlaması ---
        evaluation_date = data['evaluation_date'].replace(day=1)
        
        # 'update' zamanı mövcud obyekti yoxlamadan xaric etmək
        qs = UserEvaluation.objects.filter(
            evaluatee=evaluatee,
            evaluation_date=evaluation_date
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                f"{evaluation_date.strftime('%Y-%m')} ayı üçün bu işçiyə aid bir dəyərləndirmə artıq mövcuddur."
            )
            
        # evaluatee obyektini sonrakı mərhələlər üçün dataya əlavə edirik
        data['evaluatee'] = evaluatee
        return data