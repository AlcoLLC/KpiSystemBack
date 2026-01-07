from rest_framework import serializers
from .models import UserEvaluation
from accounts.models import User
from django.utils import timezone
import datetime
from rest_framework.exceptions import PermissionDenied

class UserEvaluationSerializer(serializers.ModelSerializer):
    evaluatee_id = serializers.IntegerField(write_only=True)
    
    evaluator = serializers.SerializerMethodField()
    evaluatee = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    evaluation_type = serializers.ChoiceField(
        choices=UserEvaluation.EvaluationType.choices, write_only=True
    )

    class Meta:
        model = UserEvaluation
        fields = [
            'id', 'evaluator', 'evaluatee', 'evaluatee_id', 'evaluation_type', 'score',
            'comment', 'evaluation_date', 'previous_score', 'updated_by',
            'history', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'evaluator', 'previous_score', 'updated_by', 
            'history', 'created_at', 'updated_at'
        ]

    def get_user_details(self, user_obj):
        position_name = user_obj.position.name if user_obj.position else None
        if user_obj:
            return {
                'id': user_obj.id,
                'full_name': user_obj.get_full_name(),
                'position_name': position_name,
            }
        return None
    
    def get_evaluator(self, obj):
        return self.get_user_details(obj.evaluator)

    def get_evaluatee(self, obj):
        return self.get_user_details(obj.evaluatee)

    def get_updated_by(self, obj):
        if obj.updated_by:
             return self.get_user_details(obj.updated_by)
        return None
    
    def validate_evaluation_date(self, value):
        return value.replace(day=1)


    def validate(self, data):
        request = self.context.get('request')
        evaluator = request.user
        
        try:
            evaluatee = User.objects.get(id=data['evaluatee_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belə bir istifadəçi tapılmadı.'})
        
        is_admin = evaluator.role == 'admin'
        
        if evaluatee.role == 'ceo':
            raise serializers.ValidationError("CEO dəyərləndirilə bilməz.")
        
        if evaluator == evaluatee:
            raise serializers.ValidationError("İstifadəçilər özlərini dəyərləndirə bilməz.")
        
        evaluation_type = data['evaluation_type']
        
        eval_config = evaluatee.get_evaluation_config()
        
        if not is_admin:
            if eval_config['superior_evaluator'] and eval_config['superior_evaluator'].id == evaluator.id:
                if evaluation_type != UserEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                    raise serializers.ValidationError(
                        'Siz bu işçinin SUPERIOR qiymətləndiricisisiniz. SUPERIOR dəyərləndirməsi etməlisiniz.'
                    )
            
            elif eval_config['is_dual_evaluation'] and eval_config['tm_evaluator'] and eval_config['tm_evaluator'].id == evaluator.id:
                if evaluation_type != UserEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
                    raise serializers.ValidationError(
                        'Siz bu işçinin Top Management qiymətləndiricisisiniz. TOP_MANAGEMENT dəyərləndirməsi etməlisiniz.'
                    )
                
                evaluation_date = data['evaluation_date'].replace(day=1)
                superior_eval_exists = UserEvaluation.objects.filter(
                    evaluatee=evaluatee,
                    evaluation_date=evaluation_date,
                    evaluation_type=UserEvaluation.EvaluationType.SUPERIOR_EVALUATION 
                ).exists()

                if self.instance and self.instance.evaluation_type == UserEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                    superior_eval_exists = True

                if not superior_eval_exists:
                    raise serializers.ValidationError(
                        {'evaluation_type': "Top Management dəyərləndirməsi yalnız SUPERIOR dəyərləndirməsi tamamlandıqdan sonra edilə bilər."}
                    )
            else:
                raise serializers.ValidationError(
                    'Bu işçini qiymətləndirməyə icazəniz yoxdur.'
                )
            
        evaluation_date = data['evaluation_date'].replace(day=1)
        qs = UserEvaluation.objects.filter(
            evaluatee=evaluatee,
            evaluation_date=evaluation_date,
            evaluation_type=evaluation_type
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                f"{evaluation_date.strftime('%Y-%m')} ayı üçün bu işçiyə aid {evaluation_type} dəyərləndirməsi artıq mövcuddur."
            )
            
        data['evaluatee'] = evaluatee
        return data

    def update(self, instance, validated_data):
        request = self.context.get('request')
        user = request.user
        new_score = validated_data.get('score')
        old_score = instance.score
        
        is_admin = user.role == 'admin'
        
        if instance.evaluation_type == 'TOP_MANAGEMENT':
            if user.role == 'ceo':
                raise PermissionDenied("CEO Top Management dəyərləndirməsini redaktə edə bilməz.")
            
            if user.role not in ['top_management', 'admin']:
                raise PermissionDenied("Bu dəyərləndirməni yalnız Top Management və ya Admin redaktə edə bilər.")
            
            if user.role == 'top_management' and instance.evaluator != user:
                raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")
        else:
            is_evaluator = instance.evaluator == user
            
            if not (is_admin or is_evaluator):
                raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")

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
    selected_month_evaluations = serializers.SerializerMethodField()
    can_evaluate_superior = serializers.SerializerMethodField()
    can_evaluate_top_management = serializers.SerializerMethodField()
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)
    evaluation_config = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'profile_photo',
            'department_name', 'role_display', 'position_name',
            'selected_month_evaluations', 'can_evaluate_superior', 'can_evaluate_top_management',
            'evaluation_config'
        ]

    def get_selected_month_evaluations(self, obj):
        evaluation_date = self.context.get('evaluation_date')
        if not evaluation_date:
            evaluation_date = timezone.now().date().replace(day=1)

        evaluations = UserEvaluation.objects.filter(
            evaluatee=obj,
            evaluation_date=evaluation_date
        )
        
        data = {}
        for evaluation_type in UserEvaluation.EvaluationType.choices:
            eval_instance = evaluations.filter(evaluation_type=evaluation_type[0]).first()
            if eval_instance:
                data[evaluation_type[0].lower()] = UserEvaluationSerializer(
                    eval_instance, 
                    context={'request': self.context.get('request')}
                ).data
            else:
                data[evaluation_type[0].lower()] = None
        return data
    
    def get_can_evaluate_superior(self, obj):
        if obj.role in ['ceo', 'admin']: 
            return False
        
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'): 
            return False
        
        evaluator = request.user
        
        if evaluator.factory_role == "top_management":
            return False
        
        if evaluator.role == 'admin': 
            return True
        
        superior_evaluator = obj.get_kpi_evaluator_by_type('SUPERIOR')
        
        result = superior_evaluator == evaluator
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[can_evaluate_superior] Evaluator: {evaluator.get_full_name()} ({evaluator.role}) -> Evaluatee: {obj.get_full_name()} ({obj.role}) -> Superior: {superior_evaluator.get_full_name() if superior_evaluator else 'None'} -> Can Evaluate: {result}")
        
        return result
    
    def get_can_evaluate(self, obj):
        if obj.role in ['ceo', 'admin']:
            return False
        
        request = self.context.get('request')

        if not request or not hasattr(request, 'user'):
            return False
        
        evaluator = request.user

        if evaluator.role == 'admin':
            if obj.id == evaluator.id:
                 return False
            if obj.role in ['ceo', 'admin']:
                 return False
            return True
        
        if evaluator.role == 'ceo':
             if obj.role == 'top_management':
                  return True
             return obj.get_kpi_evaluator() == evaluator
        
        return obj.get_kpi_evaluator() == evaluator


    def get_can_evaluate_top_management(self, obj):
        if obj.role not in ['employee', 'manager']:
            return False
            
        if obj.role in ['ceo', 'admin']: 
            return False
            
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'): 
            return False
        
        evaluator = request.user
        
        if evaluator.factory_role == "top_management":
            return False
        
        if evaluator.role == 'admin':
            return True
        
        tm_evaluator = obj.get_kpi_evaluator_by_type('TOP_MANAGEMENT')
        
        result = tm_evaluator == evaluator
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[can_evaluate_top_management] Evaluator: {evaluator.get_full_name()} ({evaluator.role}) -> Evaluatee: {obj.get_full_name()} ({obj.role}) -> TM: {tm_evaluator.get_full_name() if tm_evaluator else 'None'} -> Can Evaluate: {result}")
        
        return result
    
    def get_evaluation_config(self, obj):
        config = obj.get_evaluation_config()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Serializer - get_evaluation_config] {obj.get_full_name()} -> Config: {config}")
        
        return {
            'is_dual_evaluation': config['is_dual_evaluation'],
            'superior_evaluator_name': config['superior_evaluator_name'],
            'tm_evaluator_name': config['tm_evaluator_name'],
        }
    
class MonthlyScoreSerializer(serializers.ModelSerializer):
    evaluation_type_display = serializers.CharField(source='get_evaluation_type_display', read_only=True)
    evaluator = serializers.SerializerMethodField()
    
    class Meta:
        model = UserEvaluation
        fields = ['evaluation_date', 'score', 'evaluation_type_display', 'evaluator']
        
    def get_user_details(self, user_obj):
        position_name = user_obj.position.name if user_obj.position else None
        if user_obj:
            return {
                'id': user_obj.id,
                'full_name': user_obj.get_full_name(),
                'position_name': position_name,
            }
        return None

    def get_evaluator(self, obj):
        return self.get_user_details(obj.evaluator)