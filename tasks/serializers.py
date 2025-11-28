from rest_framework import serializers
from .models import Task, CalendarNote
from accounts.models import User
from kpis.serializers import KPIEvaluationSerializer
from accounts.serializers import UserSerializer

class TaskSerializer(serializers.ModelSerializer):
    assignee_details = serializers.StringRelatedField(source='assignee', read_only=True)
    created_by_details = serializers.StringRelatedField(source='created_by', read_only=True)
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all()) 
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    evaluations = KPIEvaluationSerializer(many=True, read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)

    assignee_obj = serializers.SerializerMethodField(read_only=True)
    created_by_obj = serializers.SerializerMethodField(read_only=True)

    evaluations_list = serializers.SerializerMethodField()
    evaluation_status = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'status',
            'priority',
            'assignee', 
            'assignee_details', 
            'position_name',
            'created_by',
            'created_by_details',
            'start_date',
            'due_date',
            'approved',
            'created_at',
            'status_display',
            'priority_display',
            'evaluations',
            'assignee_obj',
            'created_by_obj', 
            'evaluations_list', 'evaluation_status',
            
        ]
        read_only_fields = [
            'created_by',
            'created_by_details',
            'approved',
            'created_at',
        ]

    def get_assignee_obj(self, obj):
        if obj.assignee:
            return UserSerializer(obj.assignee, context=self.context).data
        return None

    def get_created_by_obj(self, obj):
        if obj.created_by:
            return UserSerializer(obj.created_by, context=self.context).data
        return None
    
    def get_evaluations_list(self, obj):
        """Tapşırığın bütün dəyərləndirmələri"""
        from kpis.serializers import KPIEvaluationSerializer
        evaluations = obj.evaluations.all().select_related('evaluator', 'evaluatee')
        return KPIEvaluationSerializer(evaluations, many=True).data
    
    def get_evaluation_status(self, obj):
        """
        Task üçün dəyərləndirmə statusunu qaytarır
        
        Returns:
            dict: {
                'hasSelfEval': bool,
                'hasSuperiorEval': bool,
                'hasTopEval': bool,
                'finalScore': int | None
            }
        """
        evaluations = obj.evaluations.all()
        
        # Hansı dəyərləndirmələr mövcuddur?
        has_self_eval = any(e.evaluation_type == 'SELF' for e in evaluations)
        has_superior_eval = any(e.evaluation_type == 'SUPERIOR' for e in evaluations)
        has_top_eval = any(e.evaluation_type == 'TOP_MANAGEMENT' for e in evaluations)
        
        # Final score hesablama
        final_score = None
        
        if obj.assignee:
            eval_config = obj.assignee.get_evaluation_config()
            
            # Dual evaluation varsa (employee və manager üçün)
            if eval_config.get('is_dual_evaluation'):
                # TOP_MANAGEMENT skorunu götür
                top_eval = next(
                    (e for e in evaluations if e.evaluation_type == 'TOP_MANAGEMENT'), 
                    None
                )
                if top_eval and top_eval.top_management_score is not None:
                    final_score = top_eval.top_management_score
                    
            # Normal evaluation (department_lead, top_management üçün)
            else:
                # SUPERIOR skorunu götür
                superior_eval = next(
                    (e for e in evaluations if e.evaluation_type == 'SUPERIOR'), 
                    None
                )
                if superior_eval and superior_eval.superior_score is not None:
                    final_score = superior_eval.superior_score
        
        return {
            'hasSelfEval': has_self_eval,
            'hasSuperiorEval': has_superior_eval,
            'hasTopEval': has_top_eval,
            'finalScore': final_score,
        }
    
class TaskAssigneeSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'position_name', 'profile_photo']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        photo_url = representation.get('profile_photo')
        if request and photo_url:
            representation['profile_photo'] = request.build_absolute_uri(photo_url)
        return representation

class TaskUserSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'position_name', 'role']

class CalendarNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarNote
        fields = ['id', 'date', 'content']
        read_only_fields = ['user']