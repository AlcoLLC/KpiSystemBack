from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department, Position, FactoryPosition
from django.contrib.auth import get_user_model, login
from django.utils.translation import gettext_lazy as _
User = get_user_model()
    
class FactoryPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FactoryPosition
        fields = '__all__'

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'name']

class OfficeUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    role_display = serializers.SerializerMethodField()
    all_departments = serializers.SerializerMethodField(read_only=True)
    position_details = serializers.SerializerMethodField()
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    user_type = serializers.SerializerMethodField()
    
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

    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "role", "role_display", 
                  "position", "department", "profile_photo", "phone_number", "password", "user_type", "factory_role",
                  "all_departments", "position_details", "top_managed_departments"]
        extra_kwargs = {
            'username': {'required': False, 'allow_blank': True}
        }
        
    def validate(self, attrs):
        if not attrs.get('username') and attrs.get('email'):
            attrs['username'] = attrs.get('email')
        return super().validate(attrs)
    
    def get_user_type(self, obj):
        if obj.factory_role:
            return "factory"
        return "office"

    def create(self, validated_data):
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        email = validated_data.get('email')
        validated_data['username'] = email 
        
        user = User.objects.create_user(password=password, **validated_data)
        
        if top_departments is not None:
            user.top_managed_departments.set(top_departments)
            
        return user
    
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
            
        try:
             if hasattr(obj, 'ceo_department') and obj.ceo_department: 
                 departments.add(obj.ceo_department.name)
        except Department.DoesNotExist:
             pass

        if hasattr(obj, 'top_managed_departments'):
            for dept in obj.top_managed_departments.all(): 
                departments.add(dept.name)
                
        return list(departments)
    
    def update(self, instance, validated_data):
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        profile_photo = validated_data.get('profile_photo')

        new_role = validated_data.get('role', instance.role)
        new_department = validated_data.get('department', instance.department)

        if 'role' in validated_data:
            if instance.role == 'manager' and new_role != 'manager':
                Department.objects.filter(manager=instance).update(manager=None)
            if instance.role == 'department_lead' and new_role != 'department_lead':
                Department.objects.filter(department_lead=instance).update(department_lead=None)
            if instance.role == 'ceo' and new_role != 'ceo': 
                Department.objects.filter(ceo=instance).update(ceo=None)
            if instance.role == 'top_management' and new_role != 'top_management':
                 instance.top_managed_departments.clear()

        if profile_photo == '':
            instance.profile_photo.delete(save=False)
            validated_data['profile_photo'] = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)
        
        instance.save()
        
        if top_departments is not None:
            instance.top_managed_departments.set(top_departments)
        
        if new_department:
            if new_role == 'manager':
                Department.objects.filter(manager=instance).exclude(id=new_department.id).update(manager=None)
                new_department.manager = instance
                new_department.save()
            elif new_role == 'department_lead':
                Department.objects.filter(department_lead=instance).exclude(id=new_department.id).update(department_lead=None)
                new_department.department_lead = instance
                new_department.save()
            elif new_role == 'ceo': 
                Department.objects.filter(ceo=instance).exclude(id=new_department.id).update(ceo=None)
                new_department.ceo = instance
                new_department.save()
        
        return instance
    
    def get_role_display(self, obj):
        if obj.factory_role:
            return obj.get_factory_role_display()
        if obj.role:
            return obj.get_role_display()
        return None

    def get_position_details(self, obj):
        if obj.factory_position:
            return {
                "id": obj.factory_position.id,
                "name": obj.factory_position.name
            }
        if obj.position:
            return {
                "id": obj.position.id,
                "name": obj.position.name
            }
        return None

class FactoryUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    factory_role_display = serializers.CharField(source='get_factory_role_display', read_only=True)
    factory_position = serializers.PrimaryKeyRelatedField(
        queryset=FactoryPosition.objects.all(), write_only=True, required=False, allow_null=True
    )
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    factory_position = serializers.PrimaryKeyRelatedField(
        queryset=FactoryPosition.objects.all(), write_only=True, required=False, allow_null=True
    )
    position_details = FactoryPositionSerializer(source='factory_position', read_only=True)
    factory_type_display = serializers.CharField(source='get_factory_type_display', read_only=True)
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "factory_role", 
                  "factory_role_display", "factory_type", "factory_position", "user_type",
                  "profile_photo",  "password", "position_details", "factory_type_display"]

    def get_user_type(self, obj):
        if obj.factory_role:
            return "factory"
        return "office"

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        email = validated_data.get('email')
        validated_data['username'] = email
        
        user = User.objects.create_user(password=password, **validated_data)
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        
        if password:
            instance.set_password(password)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance
    
    def get_position_details(self, obj):
        if obj.factory_position:
            return {
                "id": obj.factory_position.id,
                "name": obj.factory_position.name
            }
        if obj.position:
            return {
                "id": obj.position.id,
                "name": obj.position.name
            }
        return None

    def get_role_display(self, obj):
        if obj.factory_role:
            return obj.get_factory_role_display()
        elif obj.role:
            return obj.get_role_display()
        return None

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    all_departments = serializers.SerializerMethodField(read_only=True)
    position_details = serializers.SerializerMethodField()
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=True
    )
    
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(), write_only=True, required=False, allow_null=True
    )
    factory_position = serializers.PrimaryKeyRelatedField(
        queryset=FactoryPosition.objects.all(), write_only=True, required=False, allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    top_managed_departments = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), many=True, required=False
    )

    role_display = serializers.SerializerMethodField()
    factory_type_display = serializers.SerializerMethodField()
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "role", "role_display", "all_departments", 'factory_role', 
            'factory_type', 'factory_type_display', 'position', 'factory_position', 
            'position_details', "department", "first_name", "last_name", "profile_photo", 
            "phone_number", "password", "top_managed_departments", "user_type"
        ]
        read_only_fields = ['role_display', 'factory_type_display', 'all_departments', 'position_details']
        extra_kwargs = {'username': {'required': False}}

    def validate(self, attrs):
        if not attrs.get('username') and attrs.get('email'):
            attrs['username'] = attrs.get('email')
        return super().validate(attrs)

    def get_user_type(self, obj):
        if obj.factory_role:
            return "factory"
        return "office"

    def get_role_display(self, obj):
        if obj.factory_role:
            return obj.get_factory_role_display()
        elif obj.role:
            return obj.get_role_display()
        return None

    def get_factory_type_display(self, obj):
        return obj.get_factory_type_display() if obj.factory_type else None

    def get_position_details(self, obj):
        if obj.factory_position:
            return {"id": obj.factory_position.id, "name": obj.factory_position.name}
        elif obj.position:
            return {"id": obj.position.id, "name": obj.position.name}
        return None

    def get_all_departments(self, obj):
        if self.get_user_type(obj) == "factory":
            return []
        
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
            
        try:
             if hasattr(obj, 'ceo_department') and obj.ceo_department: 
                 departments.add(obj.ceo_department.name)
        except Department.DoesNotExist:
             pass

        if hasattr(obj, 'top_managed_departments'):
            for dept in obj.top_managed_departments.all(): 
                departments.add(dept.name)
                
        return list(departments)
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        if instance.factory_role:
            representation.pop('role', None)
            representation.pop('department', None)
            representation.pop('top_managed_departments', None)
        else:
            representation.pop('factory_role', None)
            representation.pop('factory_type', None)
            representation.pop('factory_type_display', None)
            
        return representation

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
        is_factory = 'factory_role' in validated_data or 'factory_type' in validated_data
        
        if 'username' not in validated_data:
            validated_data['username'] = validated_data.get('email')
        
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        
        user = User.objects.create_user(password=password, **validated_data)

        if not is_factory:
            role = validated_data.get('role')
            department = validated_data.get('department')
            
            if top_departments is not None:
                user.top_managed_departments.set(top_departments)

            if department:
                if role == 'manager':
                    Department.objects.filter(id=department.id).update(manager=user)
                elif role == 'department_lead':
                    Department.objects.filter(id=department.id).update(department_lead=user)
                elif role == 'ceo': 
                    Department.objects.filter(id=department.id).update(ceo=user)
        
        return user

    def update(self, instance, validated_data):
        is_factory = (instance.factory_role is not None) or ('factory_role' in validated_data)
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        profile_photo = validated_data.get('profile_photo')

        new_role = validated_data.get('role', instance.role)
        new_department = validated_data.get('department', instance.department)

        if not is_factory and 'role' in validated_data:
            new_role = validated_data.get('role')
            if instance.role == 'manager' and new_role != 'manager':
                Department.objects.filter(manager=instance).update(manager=None)
            if instance.role == 'department_lead' and new_role != 'department_lead':
                Department.objects.filter(department_lead=instance).update(department_lead=None)
            if instance.role == 'ceo' and new_role != 'ceo':
                Department.objects.filter(ceo=instance).update(ceo=None)
            if instance.role == 'top_management' and new_role != 'top_management':
                instance.top_managed_departments.clear()

        if profile_photo == '':
            instance.profile_photo.delete(save=False)
            validated_data['profile_photo'] = None

        instance = super().update(instance, validated_data)

        if password:
            instance.set_password(password)
        
        instance.save()
        
        if not is_factory:
            new_role = validated_data.get('role', instance.role)
            new_dept = validated_data.get('department', instance.department)
            
            if new_dept:
                if new_role == 'manager':
                    Department.objects.filter(manager=instance).exclude(id=new_dept.id).update(manager=None)
                    new_dept.manager = instance
                    new_dept.save()
                elif new_role == 'department_lead':
                    Department.objects.filter(department_lead=instance).exclude(id=new_dept.id).update(department_lead=None)
                    new_dept.department_lead = instance
                    new_dept.save()
                elif new_role == 'ceo':
                    Department.objects.filter(ceo=instance).exclude(id=new_dept.id).update(ceo=None)
                    new_dept.ceo = instance
                    new_dept.save()

            if top_departments is not None:
                instance.top_managed_departments.set(top_departments)
        
        return instance


class DepartmentSerializer(serializers.ModelSerializer):
    ceo = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='ceo'), required=False, allow_null=True
    )
    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='manager'), required=False, allow_null=True
    )
    department_lead = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='department_lead'), required=False, allow_null=True
    )
    top_management = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='top_management'), many=True, required=False, allow_null=True
    )

    class Meta:
        model = Department
        fields = ['id', 'name', 'ceo', 'manager', 'department_lead', 'top_management']

    def update(self, instance, validated_data):
        new_lead = validated_data.get('department_lead')
        if new_lead:
            Department.objects.filter(department_lead=new_lead).exclude(pk=instance.pk).update(department_lead=None)
        
        new_manager = validated_data.get('manager')
        if new_manager:
            Department.objects.filter(manager=new_manager).exclude(pk=instance.pk).update(manager=None)
            
        new_ceo = validated_data.get('ceo')
        if new_ceo:
            Department.objects.filter(ceo=new_ceo).exclude(pk=instance.pk).update(ceo=None)


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
            user = User.objects.select_related(
                'department', 'position', 'factory_position'
            ).prefetch_related('top_managed_departments').filter(email=email).first()
            
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

        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop(self.username_field, None)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField(write_only=True)