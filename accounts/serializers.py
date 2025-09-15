from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department
from rest_framework.validators import UniqueValidator

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    department_name = serializers.CharField(source='managed_department.name', read_only=True, allow_null=True)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id", "email", "role", "role_display", "department_name", 
            "first_name", "last_name", "profile_photo", "phone_number", "password"
        ]
        read_only_fields = ['role_display', 'department_name']

    def validate_email(self, value):
        """Custom email validation to handle updates correctly"""
        # Get current instance if we're updating
        current_user = self.instance
        
        # Check if email already exists, excluding current user during updates
        if current_user:
            existing_user = User.objects.filter(email=value).exclude(pk=current_user.pk).first()
        else:
            existing_user = User.objects.filter(email=value).first()
        
        if existing_user:
            raise serializers.ValidationError("Bu e-poçt ünvanı artıq istifadə olunur.")
        
        return value

    def update(self, instance, validated_data):
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.role = validated_data.get('role', instance.role)
        instance.phone_number = validated_data.get('phone_number', instance.phone_number)
        
        # Handle profile photo
        if 'profile_photo' in validated_data:
            instance.profile_photo = validated_data.get('profile_photo')
        
        # Handle password
        password = validated_data.get('password')
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance
    
    def create(self, validated_data):
        if 'username' not in validated_data:
            validated_data['username'] = validated_data['email']
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        return user
    

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            # Get the first active user with this email (or add additional filters)
            user = User.objects.filter(email=email, is_active=True).first()
            if not user:
                raise serializers.ValidationError("Bu email ilə aktiv istifadəçi tapılmadı.")
        except Exception:
            raise serializers.ValidationError("Bu email ilə istifadəçi tapılmadı.")

        if not user.check_password(password):
            raise serializers.ValidationError("Şifrə yanlışdır.")

        if not user.is_active:
            raise serializers.ValidationError("İstifadəçi aktiv deyil.")
            
        data = super().validate(attrs={self.username_field: user.get_username(), "password": password})

        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop(self.username_field, None)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField(write_only=True)