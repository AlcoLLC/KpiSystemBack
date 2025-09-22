from rest_framework import serializers
from .models import KPIEvaluation
from accounts.models import User

class KPIEvaluationSerializer(serializers.ModelSerializer):
    evaluator_info = serializers.StringRelatedField(source='evaluator', read_only=True)
    evaluatee_info = serializers.StringRelatedField(source='evaluatee', read_only=True)
    task_info = serializers.StringRelatedField(source='task', read_only=True)

    class Meta:
        model = KPIEvaluation
        fields = [
            'id', 'task', 'evaluator', 'evaluatee', 'score', 'self_score', 
            'comment', 'created_at', 'evaluation_type',
            'evaluator_info', 'evaluatee_info', 'task_info'
        ]
        read_only_fields = ['evaluator', 'evaluation_type']

    def validate(self, data):
        evaluator = self.context['request'].user
        evaluatee = data.get('evaluatee')
        
        # Öz-qiymətləndirmə
        if evaluator == evaluatee:
            if 'self_score' not in self.initial_data or self.initial_data.get('self_score') is None:
                raise serializers.ValidationError("Öz dəyərləndirməniz üçün 'self_score' sahəsini doldurmalısınız.")
            if 'score' in self.initial_data and self.initial_data.get('score') is not None:
                raise serializers.ValidationError("'score' sahəsi yalnız rəhbər tərəfindən doldurula bilər.")
        
        # Rəhbər qiymətləndirməsi
        else:
            if 'score' not in self.initial_data or self.initial_data.get('score') is None:
                raise serializers.ValidationError("Rəhbər dəyərləndirməsi üçün 'score' sahəsini doldurmalısınız.")
            if 'self_score' in self.initial_data and self.initial_data.get('self_score') is not None:
                raise serializers.ValidationError("'self_score' sahəsi yalnız işçinin özü tərəfindən doldurula bilər.")
        
        return data