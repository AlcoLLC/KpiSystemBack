from rest_framework import serializers
from .models import KPIEvaluation
from accounts.models import User
from accounts.serializers import UserSerializer
from tasks.models import Task
from tasks.serializers import TaskSerializer

class KPIEvaluationSerializer(serializers.ModelSerializer):
    evaluator = UserSerializer(read_only=True)
    evaluator_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        source="evaluator", 
        write_only=True, 
        required=False
    )
    evaluatee = UserSerializer(read_only=True)
    evaluatee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="evaluatee", write_only=True
    )

    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), source="task", write_only=True
    )
    
    temp_score = serializers.IntegerField(write_only=True, required=False)
    final_score = serializers.SerializerMethodField()

    class Meta:
        model = KPIEvaluation
        fields = [
            "id", "task", "task_id",
            "evaluator", "evaluator_id",
            "evaluatee", "evaluatee_id",
            "score", "self_evaluation_score", "temp_score", "final_score",
            "comment", "created_at", "updated_at",
            "evaluation_type", "is_superior_evaluated"
        ]
        read_only_fields = ["created_at", "updated_at", "is_superior_evaluated"]

    def get_final_score(self, obj):
        return obj.get_final_score()

    def create(self, validated_data):
        temp_score = validated_data.pop('temp_score', None)
        evaluation_type = validated_data.get('evaluation_type')
        
        if evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION and temp_score:
            instance = KPIEvaluation(**validated_data)
            instance._temp_score = temp_score
            instance.save()
            return instance
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        temp_score = validated_data.pop('temp_score', None)
        evaluation_type = validated_data.get('evaluation_type', instance.evaluation_type)
        
        if evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION and temp_score:
            validated_data['score'] = temp_score
            
        return super().update(instance, validated_data)

    def validate_temp_score(self, value):
        evaluation_type = self.initial_data.get('evaluation_type')
        
        if evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
            if value < 1 or value > 10:
                raise serializers.ValidationError("Öz değerlendirme skoru 1-10 arasında olmalıdır.")
        elif evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
            if value < 1 or value > 100:
                raise serializers.ValidationError("Üst değerlendirme skoru 1-100 arasında olmalıdır.")
                
        return value
