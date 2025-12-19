from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Position
from django.contrib.auth import get_user_model, login
from django.utils.text import slugify

User = get_user_model()

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'name']

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    factory_display = serializers.CharField(source='get_factory_type_display', read_only=True)
    position_details = PositionSerializer(source='position', read_only=True)
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=True
    )
    
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(), write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = User
        fields = [
            "id", "email", "role", "role_display", "factory_type", "factory_display",
            "position", "position_details", "first_name", "last_name", 
            "profile_photo", "phone_number", "password", "slug"
        ]
        read_only_fields = ['role_display', 'factory_display', 'position_details', 'slug']

    def validate_email(self, value):
        current_user = self.instance
        qs = User.objects.filter(email=value)
        if current_user:
            qs = qs.exclude(pk=current_user.pk)
        
        if qs.exists():
            raise serializers.ValidationError("Bu e-poçt ünvanı artıq istifadə olunur.")
        return value

    def create(self, validated_data):
        # Email-i username kimi istifadə edirik
        if 'username' not in validated_data:
            validated_data['username'] = validated_data.get('email')
        
        password = validated_data.pop('password', None)
        user = User.objects.create_user(password=password, **validated_data)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        profile_photo = validated_data.get('profile_photo')

        # Şəkil silmə məntiqi
        if profile_photo == '':
            if instance.profile_photo:
                instance.profile_photo.delete(save=False)
            validated_data['profile_photo'] = None

        instance = super().update(instance, validated_data)

        if password:
            instance.set_password(password)
            instance.save()
        
        return instance

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Login üçün email və password tələb edirik
        self.fields.pop(self.username_field, None)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        

        user = User.objects.filter(email=email).first()
        
        if not user:
            raise serializers.ValidationError({"email": "Bu email ilə istifadəçi tapılmadı."})

        if not user.check_password(password):
            raise serializers.ValidationError({"password": "Şifrə yanlışdır."})

        if not user.is_active:
            raise serializers.ValidationError({"detail": "İstifadəçi aktiv deyil."})

        # SimpleJWT üçün lazımi username field-i set edirik
        attrs[self.username_field] = user.get_username()
        data = super().validate(attrs)

        # Login məntiqi (session istifadə edilirsə)
        request = self.context.get('request')
        if request:
            login(request, user)

        user_serializer = UserSerializer(user, context=self.context)
        data['user'] = user_serializer.data
        
        return data
    