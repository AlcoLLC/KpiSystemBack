from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department, Position
from rest_framework.validators import UniqueValidator

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'name']

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    all_departments = serializers.SerializerMethodField()

    position_details = PositionSerializer(source='position', read_only=True)
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(), write_only=True, required=False, allow_null=True
    )

    password = serializers.CharField(write_only=True, required=False)
    profile_photo = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "role", "role_display", 
            "all_departments",  'position', 'position_details',
            "first_name", "last_name", "profile_photo", "phone_number", "password"
        ]
        read_only_fields = ['role_display', 'all_departments', 'position_details']

    def get_all_departments(self, obj):
        departments = set()

        if obj.department:
            departments.add(obj.department.name)

        if hasattr(obj, 'managed_department') and obj.managed_department:
            departments.add(obj.managed_department.name)

       
        if hasattr(obj, 'led_department') and obj.led_department:
            departments.add(obj.led_department.name)

        
        if hasattr(obj, 'top_managed_departments'):
            for dept in obj.top_managed_departments.all():
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

    def update(self, instance, validated_data):
        # ModelSerializer'ın varsayılan update metodu çoğu alanı halleder.
        # Sadece özel işlem gerektiren 'password' alanını yönetmemiz yeterli.
        password = validated_data.pop('password', None)
        
        # Üst sınıfın update'ini çağırarak diğer alanların güncellenmesini sağlayın
        instance = super().update(instance, validated_data)

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