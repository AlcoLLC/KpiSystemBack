from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department, Profile

class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    department_name = serializers.CharField(source='managed_department.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "role_display", "department_name", "first_name", "last_name"]
        read_only_fields = ['role_display', 'department_name']


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
            user = User.objects.get(email=email)
        except User.DoesNotExist:
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
    
class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True) 

    email = serializers.EmailField(source='user.email', required=False)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Profile
        fields = [
            'id',
            'user',
            'phone_number',
            'profile_photo',
            'email',
            'first_name',
            'last_name',
            'password',
        ]

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        password = validated_data.pop('password', None) 

        user = instance.user

        user.first_name = user_data.get('first_name', user.first_name)
        user.last_name = user_data.get('last_name', user.last_name)
        user.email = user_data.get('email', user.email)

        if password:
            user.set_password(password)
        
        user.save()
        return super().update(instance, validated_data)