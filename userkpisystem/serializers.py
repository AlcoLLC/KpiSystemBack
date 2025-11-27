from rest_framework import serializers
from .models import UserEvaluation
from accounts.models import User
from django.utils import timezone
import datetime
from rest_framework.exceptions import PermissionDenied

class UserEvaluationSerializer(serializers.ModelSerializer):
    evaluatee_id = serializers.IntegerField(write_only=True)
    
    # StringRelatedField yerine get_user_details metodu kullanılacak
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
    
    # GÜNCELLENDİ: StringRelatedField'ler SeriliazerMethodField ile değiştirildi
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

    # ... (UserEvaluationSerializer sinfində)

    def validate(self, data):
        request = self.context.get('request')
        evaluator = request.user
        
        try:
            evaluatee = User.objects.get(id=data['evaluatee_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError({'evaluatee_id': 'Belə bir istifadəçi tapılmadı.'})
        
        # YENİ/GÜNCELLENDİ: Top Management yalnızca CEO veya Admin tarafından değerlendirilebilir
        is_admin_or_ceo = evaluator.role in ['ceo', 'admin']
        
        if evaluatee.role == 'ceo':
            raise serializers.ValidationError("CEO dəyərləndirilə bilməz.")
        
        if evaluator == evaluatee:
            raise serializers.ValidationError("İstifadəçilər özlərini dəyərləndirə bilməz.")
        
        evaluation_type = data['evaluation_type']
        
        # --- YENİ MƏNTİQ: TM DƏYƏRLƏNDİRMƏSİNDƏN ƏVVƏL SUPERIOR YOXLANILMASI ---
        if evaluation_type == UserEvaluation.EvaluationType.TOP_MANAGEMENT_EVALUATION:
            if evaluatee.role in ['employee', 'manager']: # Yalnız bu rollar üçün TM qiymətləndirməsi tətbiq olunur
                superior_eval_exists = UserEvaluation.objects.filter(
                    evaluatee=evaluatee,
                    evaluation_date=data['evaluation_date'].replace(day=1),
                    # Düzgün müraciət: Dəyərin string adı
                    evaluation_type=UserEvaluation.EvaluationType.SUPERIOR_EVALUATION 
                ).exists()

                # Yeniləmə əməliyyatında cari dəyərləndirməni nəzərə alırıq
                if self.instance and self.instance.evaluation_type == UserEvaluation.EvaluationType.SUPERIOR_EVALUATION:
                     superior_eval_exists = True # Əgər SUPERIOR qiymətləndirməsi yenilənirsə, onun mövcudluğu təsdiqlənir

                if not superior_eval_exists:
                    raise serializers.ValidationError(
                        {'evaluation_type': "Top Management dəyərləndirməsi yalnız Üst Rəhbər dəyərləndirməsi tamamlandıqdan sonra edilə bilər."}
                    )
        # ---------------------------------------------------------------------

        required_evaluator = evaluatee.get_kpi_evaluator_by_type(evaluation_type) # Yeni metod istifadə edilir
        
        # ... (icazə yoxlaması eyni qalır)
        if not is_admin_or_ceo:
            # ... (required_evaluator yoxlaması)
            if required_evaluator != evaluator:
                raise serializers.ValidationError(
                    f"Yalnız işçinin {evaluation_type} iyerarxiyasındakı rəhbəri və ya Admin/CEO dəyərləndirmə edə bilər."
                )
            
        evaluation_date = data['evaluation_date'].replace(day=1)
        qs = UserEvaluation.objects.filter(
            evaluatee=evaluatee,
            evaluation_date=evaluation_date,
            evaluation_type=evaluation_type # Yeni: evaluation_type əsasında unikal yoxlama
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
        
        # Redaktə icazəsi yoxlaması
        is_admin = user.role == 'admin'
        
        # TOP_MANAGEMENT dəyərləndirməsini yalnız TM və Admin redaktə edə bilər
        if instance.evaluation_type == 'TOP_MANAGEMENT':
            if user.role == 'ceo':
                raise PermissionDenied("CEO Top Management dəyərləndirməsini redaktə edə bilməz.")
            
            if user.role not in ['top_management', 'admin']:
                raise PermissionDenied("Bu dəyərləndirməni yalnız Top Management və ya Admin redaktə edə bilər.")
            
            # TM özü redaktə edirsə, evaluator olmalıdır
            if user.role == 'top_management' and instance.evaluator != user:
                raise PermissionDenied("Bu dəyərləndirməni redaktə etməyə icazəniz yoxdur.")
        else:
            # SUPERIOR dəyərləndirməsi üçün köhnə qaydalar
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

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'profile_photo',
            'department_name', 'role_display', 'position_name',
            'selected_month_evaluations', 'can_evaluate_superior', 'can_evaluate_top_management'
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
        
        # Admin icazəsi
        if evaluator.role == 'admin': 
            return True
        
        # CEO yalnız boşluqdakı işçiləri dəyərləndirə bilər
        if evaluator.role == 'ceo':
            # Üstü olub-olmadığını yoxla
            has_other_superior = False
            
            if obj.role == 'employee':
                if obj.department and (obj.department.manager or obj.department.department_lead):
                    has_other_superior = True
            elif obj.role == 'manager':
                if obj.department and obj.department.department_lead:
                    has_other_superior = True
            elif obj.role == 'department_lead':
                if obj.department and obj.department.top_management.exists():
                    has_other_superior = True
            
            return not has_other_superior
        
        # Top Management yalnız öz departamentindəki Department Lead-ləri dəyərləndirə bilər
        if evaluator.role == 'top_management':
            managed_departments = evaluator.top_managed_departments.all()
            if not managed_departments.exists():
                return False
            if obj.department not in managed_departments:
                return False
            # Yalnız Department Lead
            if obj.role != 'department_lead':
                return False
            return True
        
        # Digər rəhbərlər üçün standart yoxlama
        return obj.get_kpi_evaluator_by_type('SUPERIOR') == evaluator
    
    def get_can_evaluate(self, obj):
        if obj.role in ['ceo', 'admin']: # GÜNCELLENDİ: CEO ve Admin de değerlendirilemez
            return False
        
        request = self.context.get('request')

        if not request or not hasattr(request, 'user'):
            return False
        
        evaluator = request.user

        if evaluator.role == 'admin':
            if obj.id == evaluator.id:
                 return False
            # Admin, Top Management hariç herkesi değerlendirebilir (CEO'yu da hariç tutalım)
            if obj.role in ['ceo', 'admin']:
                 return False
            return True
        
        # YENİ: CEO, Top Management'ı değerlendirebilir
        if evaluator.role == 'ceo':
             if obj.role == 'top_management':
                  return True
             # CEO, hiyerarşide boşlukta kalan herhangi birini de değerlendirebilir
             return obj.get_kpi_evaluator() == evaluator
        
        # Diğer roller için standart KPI değerlendirici kuralı
        return obj.get_kpi_evaluator() == evaluator


    def get_can_evaluate_top_management(self, obj):
        # ƏSAS DƏYİŞİKLİK: Top Management dəyərləndirməsi yalnız Employee və Manager üçün
        if obj.role not in ['employee', 'manager']:
            return False
            
        if obj.role in ['ceo', 'admin']: 
            return False
            
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'): 
            return False
        
        evaluator = request.user
        
        # Admin icazəsi
        if evaluator.role == 'admin':
            return True
        
        # YALNIZ Top Management TM dəyərləndirməsi edə bilər
        if evaluator.role == 'top_management':
            # TM yalnız öz departamentindəki Employee və Manager-ləri dəyərləndirə bilər
            managed_departments = evaluator.top_managed_departments.all()
            if not managed_departments.exists():
                return False
            if obj.department not in managed_departments:
                return False
            return True
        
        # CEO və digər rollar TM dəyərləndirməsi edə bilməz
        return False
    
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