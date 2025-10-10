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
        return value.replace(day=1)

    def validate(self, data):
        request = self.context.get('request')
        evaluator = request.user
        
        try:
            evaluatee = User.objects.get(id=data['evaluatee_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belə bir istifadəçi tapılmadı.'})

        if evaluator == evaluatee:
            raise serializers.ValidationError("İstifadəçilər özlərini dəyərləndirə bilməz.")
        
        kpi_evaluator = evaluatee.get_kpi_evaluator()
        is_admin = evaluator.role == 'admin'

        if not is_admin and kpi_evaluator != evaluator:
            raise serializers.ValidationError(
                "Yalnız işçinin KPI iyerarxiyasındakı birbaşa rəhbəri və ya Admin dəyərləndirmə edə bilər."
            )
        
        evaluation_date = data['evaluation_date'].replace(day=1)
        
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
            
        data['evaluatee'] = evaluatee
        return data
    def get_user_details(self, user_obj):
        if user_obj:
            return {
                'id': user_obj.id,
                'full_name': user_obj.get_full_name(),
                'position': user_obj.position,
            }
        return None
    
    def get_evaluator(self, obj):
        return self.get_user_details(obj.evaluator)

    def get_evaluatee(self, obj):
        return self.get_user_details(obj.evaluatee)

    def get_updated_by(self, obj):
        return self.get_user_details(obj.updated_by)
    
    def update(self, instance, validated_data):
        request = self.context.get('request')
        user = request.user
        new_score = validated_data.get('score')
        old_score = instance.score

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
            
            instance.previous_score = old_score
            instance.updated_by = user

        instance.comment = validated_data.get('comment', instance.comment)
        instance.score = new_score if new_score is not None else old_score
        instance.save()
        
        return instance

class UserForEvaluationSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    selected_month_evaluation = serializers.SerializerMethodField()
    can_evaluate = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'profile_photo',
            'department_name', 'role_display', 'selected_month_evaluation',
            'can_evaluate', 'position',
        ]

    def get_selected_month_evaluation(self, obj):
        evaluation_date = self.context.get('evaluation_date')

        if not evaluation_date:
            today = timezone.now().date()
            evaluation_date = today.replace(day=1)

        evaluation = UserEvaluation.objects.filter(
            evaluatee=obj,
            evaluation_date=evaluation_date
        ).first()

        if evaluation:
            return UserEvaluationSerializer(evaluation).data
        return None
    
    def get_can_evaluate(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return False
        
        evaluator = request.user

        if evaluator.role == 'admin':
            return obj.role != 'top_management'
        
        return obj.get_kpi_evaluator() == evaluator
    
class MonthlyScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserEvaluation
        fields = ['evaluation_date', 'score']