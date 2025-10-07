# performance/serializers.py

from rest_framework import serializers
from .models import UserEvaluation
from accounts.models import User
from django.utils import timezone
import datetime

class UserEvaluationSerializer(serializers.ModelSerializer):
    evaluatee_id = serializers.IntegerField(write_only=True)
    
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
        # Artıq gələcək tarix yoxlaması burada edilmir, çünki istənilən ay seçilə bilər.
        # Tarixi hər zaman ayın 1-i olaraq normallaşdırırıq.
        return value.replace(day=1)

    def validate(self, data):
        # ... (validate metodunuz olduğu kimi qalır, dəyişikliyə ehtiyac yoxdur)
        # ...
        return data
    
    def update(self, instance, validated_data):
        """
        Yeniləmə zamanı tarixçəni (history) avtomatik idarə edir.
        """
        request = self.context.get('request')
        user = request.user
        new_score = validated_data.get('score')
        old_score = instance.score

        # Yalnız skor dəyişibsə tarixçəyə əlavə et
        if new_score is not None and old_score != new_score:
            history_entry = {
                "timestamp": timezone.now().isoformat(),
                "updated_by_id": user.id,
                "updated_by_name": user.get_full_name() or user.username,
                "previous_score": old_score,
                "new_score": new_score
            }
            if not isinstance(instance.history, list):
                instance.history = []
            instance.history.append(history_entry)
            
            # Əsas sahələri yenilə
            instance.previous_score = old_score
            instance.updated_by = user

        # Digər sahələri yenilə (məsələn, comment)
        instance.comment = validated_data.get('comment', instance.comment)
        instance.score = new_score if new_score is not None else old_score
        instance.save()
        
        return instance


class UserForEvaluationSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    # Adı daha anlaşıqlı etdik
    selected_month_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'profile_photo',
            'department_name', 'role_display', 'selected_month_evaluation'
        ]

    def get_selected_month_evaluation(self, obj):
        # View-dan göndərilən `evaluation_date` kontekstini alırıq
        evaluation_date = self.context.get('evaluation_date')

        if not evaluation_date:
            today = timezone.now().date()
            evaluation_date = today.replace(day=1)

        evaluation = UserEvaluation.objects.filter(
            evaluatee=obj,
            evaluation_date=evaluation_date
        ).first()

        if evaluation:
            # UserEvaluationSerializer istifadə edərək məlumatı formatlayırıq
            return UserEvaluationSerializer(evaluation).data
        return None