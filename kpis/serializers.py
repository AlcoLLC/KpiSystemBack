from rest_framework import serializers
from .models import KPIEvaluation
from tasks.models import Task
from accounts.models import User

class KPIEvaluationSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(write_only=True)
    evaluatee_id = serializers.IntegerField(write_only=True)
    evaluator_id = serializers.IntegerField(write_only=True, required=False)
    
    # Read-only fields for display
    task = serializers.SerializerMethodField(read_only=True)
    evaluator = serializers.SerializerMethodField(read_only=True)
    evaluatee = serializers.SerializerMethodField(read_only=True)
    
    # Score fields
    score = serializers.IntegerField(write_only=True)  # Frontend-dən gələn skor
    
    class Meta:
        model = KPIEvaluation
        fields = [
            'id', 'task_id', 'task', 'evaluator_id', 'evaluator', 
            'evaluatee_id', 'evaluatee', 'score', 'self_score', 
            'superior_score', 'final_score', 'comment', 
            'evaluation_type', 'created_at', 'updated_at',
            'updated_by', 'history'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'final_score',
                            'updated_by', 'history'
                            ]

    def get_task(self, obj):
        if obj.task:
            return {
                'id': obj.task.id,
                'title': obj.task.title,
                'description': obj.task.description,
            }
        return None

    def get_evaluator(self, obj):
        if obj.evaluator:
            return {
                'id': obj.evaluator.id,
                'username': obj.evaluator.username,
                'full_name': obj.evaluator.get_full_name(),
            }
        return None

    def get_evaluatee(self, obj):
        if obj.evaluatee:
            return {
                'id': obj.evaluatee.id,
                'username': obj.evaluatee.username,
                'full_name': obj.evaluatee.get_full_name(),
            }
        return None

    def validate(self, data):
        task_id = data.get('task_id')
        evaluatee_id = data.get('evaluatee_id')
        score = data.get('score')
        
        if not task_id:
            raise serializers.ValidationError({'task_id': 'Bu alan tələb olunur.'})
        
        if not evaluatee_id:
            raise serializers.ValidationError({'evaluatee_id': 'Bu alan tələb olunur.'})
            
        if not score:
            raise serializers.ValidationError({'score': 'Skor tələb olunur.'})

        # Task mövcudluğunu yoxla
        try:
            task = Task.objects.get(id=task_id)
            data['task'] = task
        except Task.DoesNotExist:
            raise serializers.ValidationError({'task_id': 'Belirtilen görev bulunamadı.'})

        # Evaluatee mövcudluğunu yoxla
        try:
            evaluatee = User.objects.get(id=evaluatee_id)
            data['evaluatee'] = evaluatee
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belirtilen kullanıcı bulunamadı.'})

        return data

    def create(self, validated_data):
        # Extract write-only fields
        task = validated_data.pop('task')
        evaluatee = validated_data.pop('evaluatee')
        score = validated_data.pop('score')
        
        # Set the task and evaluatee
        validated_data['task'] = task
        validated_data['evaluatee'] = evaluatee
        
        # Set score based on evaluation type
        evaluation_type = validated_data.get('evaluation_type')
        if evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
            validated_data['self_score'] = score
        else:
            validated_data['superior_score'] = score
        
        return super().create(validated_data)