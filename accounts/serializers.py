from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department, Position
from django.contrib.auth import get_user_model, login
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'name']

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    all_departments = serializers.SerializerMethodField(read_only=True)
    position_details = PositionSerializer(source='position', read_only=True)
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=True
    )
    
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(), write_only=True, required=False, allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )

    top_managed_departments = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), many=True, required=False 
        
    )

    ceo_managed_departments = serializers.PrimaryKeyRelatedField( 
        queryset=Department.objects.all(), many=True, required=False
    )

    class Meta:
        model = User
        fields = [
            "id", "email", "role", "role_display", "all_departments", 
            'position', 'position_details', "department", "first_name", "last_name", 
            "profile_photo", "phone_number", "password", "top_managed_departments",
            "ceo_managed_departments",
        ]
        read_only_fields = ['role_display', 'all_departments', 'position_details']

    def get_all_departments(self, obj):
        departments = set()
        
        if obj.department: 
            departments.add(obj.department.name)
        
        try:
            if hasattr(obj, 'managed_department') and obj.managed_department: 
                departments.add(obj.managed_department.name)
        except Department.DoesNotExist:
            pass 
        
        try:
            if hasattr(obj, 'led_department') and obj.led_department: 
                departments.add(obj.led_department.name)
        except Department.DoesNotExist:
            pass

        if hasattr(obj, 'top_managed_departments'):
            for dept in obj.top_managed_departments.all(): 
                departments.add(dept.name)

        if hasattr(obj, 'ceo_managed_departments'):
            for dept in obj.ceo_managed_departments.all(): 
                departments.add(dept.name)
                
        return list(departments)

    def validate_email(self, value):
        current_user = self.instance
        if current_user:
            existing_user = User.objects.filter(email=value).exclude(pk=current_user.pk).first()
        else:
            existing_user = User.objects.filter(email=value).first()
            
        if existing_user:
            raise serializers.ValidationError("Bu e-poçt ünvanı artıq istifadə olunur.")
        return value

    def create(self, validated_data):
        if 'username' not in validated_data:
            validated_data['username'] = validated_data.get('email')
        
        top_departments = validated_data.pop('top_managed_departments', None)
        ceo_departments = validated_data.pop('ceo_managed_departments', None)
        password = validated_data.pop('password', None)
        
        role = validated_data.get('role')
        department = validated_data.get('department')

        user = User.objects.create_user(password=password, **validated_data)

        if department:
            if role == 'manager':
                Department.objects.filter(id=department.id).update(manager=user)
            elif role == 'department_lead':
                Department.objects.filter(id=department.id).update(department_lead=user)

        if top_departments is not None:
            user.top_managed_departments.set(top_departments)

        if ceo_departments is not None:
            user.ceo_managed_departments.set(ceo_departments)
        
        return user

    def update(self, instance, validated_data):
        top_departments = validated_data.pop('top_managed_departments', None)
        ceo_departments = validated_data.pop('ceo_managed_departments', None)
        password = validated_data.pop('password', None)
        profile_photo = validated_data.get('profile_photo')

        new_role = validated_data.get('role', instance.role)
        new_department = validated_data.get('department', instance.department)

        if 'role' in validated_data and instance.role == 'manager' and new_role != 'manager':
            Department.objects.filter(manager=instance).update(manager=None)

        if 'role' in validated_data and instance.role == 'department_lead' and new_role != 'department_lead':
            Department.objects.filter(department_lead=instance).update(department_lead=None)
        
        if profile_photo == '':
            instance.profile_photo.delete(save=False)
            validated_data['profile_photo'] = None

        instance = super().update(instance, validated_data)

        if password:
            instance.set_password(password)
        
        instance.save()

        if new_department:
            if new_role == 'manager':
                Department.objects.filter(manager=instance).exclude(id=new_department.id).update(manager=None)
                new_department.manager = instance
                new_department.save()
            
            elif new_role == 'department_lead':
                Department.objects.filter(department_lead=instance).exclude(id=new_department.id).update(department_lead=None)
                new_department.department_lead = instance
                new_department.save()

        if top_departments is not None:
            instance.top_managed_departments.set(top_departments)

        if ceo_departments is not None:
            instance.ceo_managed_departments.set(ceo_departments)
        
        return instance


class DepartmentSerializer(serializers.ModelSerializer):
    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='manager'), required=False, allow_null=True
    )
    department_lead = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='department_lead'), required=False, allow_null=True
    )
    top_management = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='top_management'), many=True, required=False, allow_null=True
    )

    ceo = serializers.PrimaryKeyRelatedField( 
        queryset=User.objects.filter(role='ceo'), many=True, required=False, allow_null=True
    )

    class Meta:
        model = Department
        fields = ['id', 'name', 'manager', 'department_lead', 'top_management', 'ceo']

    def update(self, instance, validated_data):
        new_lead = validated_data.get('department_lead')
        if new_lead:
            Department.objects.filter(department_lead=new_lead).exclude(pk=instance.pk).update(department_lead=None)
        
        new_manager = validated_data.get('manager')
        if new_manager:
            Department.objects.filter(manager=new_manager).exclude(pk=instance.pk).update(manager=None)

        return super().update(instance, validated_data)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            user = User.objects.filter(email=email).first()
            if not user:
                raise serializers.ValidationError("Bu email ilə istifadəçi tapılmadı.")
        except Exception:
            raise serializers.ValidationError("Bu email ilə istifadəçi tapılmadı.")

        if not user.check_password(password):
            raise serializers.ValidationError("Şifrə yanlışdır.")

        if not user.is_active:
            raise serializers.ValidationError("İstifadəçi aktiv deyil.")
            
        data = super().validate(attrs={self.username_field: user.get_username(), "password": password})

        request = self.context.get('request')
        
        if request:
            login(request, user)
            pass

        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop(self.username_field, None)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField(write_only=True)
