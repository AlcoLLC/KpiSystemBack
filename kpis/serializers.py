from rest_framework import serializers
from .models import KPIEvaluation
from tasks.models import Task
from accounts.models import User
from django.db import models

class KPIEvaluationSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(write_only=True)
    evaluatee_id = serializers.IntegerField(write_only=True)
    evaluator_id = serializers.IntegerField(write_only=True, required=False)
    
    task = serializers.SerializerMethodField(read_only=True)
    evaluator = serializers.SerializerMethodField(read_only=True)
    evaluatee = serializers.SerializerMethodField(read_only=True)

    attachment = serializers.FileField(required=False, allow_null=True, use_url=True)
    score = serializers.IntegerField(write_only=True) 
    
    class Meta:
        model = KPIEvaluation
        fields = [
            'id', 'task_id', 'task', 'evaluator_id', 'evaluator', 
            'evaluatee_id', 'evaluatee', 'score', 'self_score', 
            'superior_score', 'top_management_score', 'final_score', 'comment', 
            'evaluation_type', 'created_at', 'updated_at',
            'updated_by', 'history', 'attachment'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'final_score',
                            'updated_by', 'history'
                            ]

    def get_task(self, obj):
        if not hasattr(obj, 'task'):
            return None
        if obj.task:
            return {
                'id': obj.task.id,
                'title': obj.task.title,
                'description': obj.task.description,
            }
        return None

    def get_evaluator(self, obj):
        if not hasattr(obj, 'evaluator') or isinstance(obj, models.Manager) or not obj.evaluator:
            return None
        
        position_name = obj.evaluator.position.name if obj.evaluator.position else None
        return {
            'id': obj.evaluator.id,
            'username': obj.evaluator.username,
            'full_name': obj.evaluator.get_full_name(),
            'position_name': position_name,
        }

    def get_evaluatee(self, obj):
        if not hasattr(obj, 'evaluatee') or isinstance(obj, models.Manager) or not obj.evaluatee:
            return None
        
        position_name = obj.evaluatee.position.name if obj.evaluatee.position else None
        return {
            'id': obj.evaluatee.id,
            'username': obj.evaluatee.username,
            'full_name': obj.evaluatee.get_full_name(),
            'position_name': position_name,
        }

    def validate(self, data):
        task_id = data.get('task_id')
        evaluatee_id = data.get('evaluatee_id')
        score = data.get('score')
        
        if not task_id:
            raise serializers.ValidationError({'task_id': 'Bu alan tələb olunur.'})
        
        if not evaluatee_id:
            raise serializers.ValidationError({'evaluatee_id': 'Bu alan tələb olunur.'})
            
        is_creating = self.instance is None
        if is_creating and not data.get('score'):
            raise serializers.ValidationError({'score': 'Skor tələb olunur.'})

        try:
            task = Task.objects.get(id=task_id)
            data['task'] = task
        except Task.DoesNotExist:
            raise serializers.ValidationError({'task_id': 'Belirtilen görev bulunamadı.'})

        try:
            evaluatee = User.objects.get(id=evaluatee_id)
            data['evaluatee'] = evaluatee
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belirtilen kullanıcı bulunamadı.'})

        return data

    def create(self, validated_data):
        task = validated_data.pop('task')
        evaluatee = validated_data.pop('evaluatee')
        score = validated_data.pop('score', None)

        validated_data.pop('task_id', None)
        validated_data.pop('evaluatee_id', None)
        
        validated_data['task'] = task
        validated_data['evaluatee'] = evaluatee
        
        evaluation_type = validated_data.get('evaluation_type')
        
        if evaluation_type == KPIEvaluation.EvaluationType.SELF_EVALUATION:
            validated_data['self_score'] = score
            
        elif evaluation_type == KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION:
            validated_data['superior_score'] = score
            
        elif evaluation_type == KPIEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
            validated_data['top_management_score'] = score
            
        return super().create(validated_data)