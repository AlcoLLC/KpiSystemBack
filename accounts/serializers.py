from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Department, Position  # Modellərin import edildiyinə əmin olun
from django.contrib.auth import get_user_model

# User modelini düzgün əldə etmək üçün (best practice)
User = get_user_model()


class PositionSerializer(serializers.ModelSerializer):
    """
    Vəzifə modeli üçün serializer.
    """
    class Meta:
        model = Position
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    """
    Genişləndirilmiş User modeli üçün əsas serializer.
    """
    email = serializers.EmailField(required=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    all_departments = serializers.SerializerMethodField(read_only=True)
    position_details = PositionSerializer(source='position', read_only=True)
    profile_photo = serializers.FileField(required=False, allow_null=True, use_url=True)
    
    # Şifrə sahəsi: yazma (write_only), tələb olunmur (required=False)
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=True
    )
    
    # Əlaqəli sahələr (ID kimi yazmaq üçün)
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
        fields = [
            "id", "email", "role", "role_display", "all_departments", 
            'position', 'position_details', "department", "first_name", "last_name", 
            "profile_photo", "phone_number", "password", "top_managed_departments"
        ]
        read_only_fields = ['role_display', 'all_departments', 'position_details']

    def get_all_departments(self, obj):
        """
        İstifadəçinin əlaqəli olduğu bütün departament adlarını çəkir.
        500 xətasının qarşısını almaq üçün `try...except` istifadə edir.
        """
        departments = set()
        
        # 1. İstifadəçinin aid olduğu departament
        if obj.department: 
            departments.add(obj.department.name)
        
        # 2. İdarə etdiyi departament (Manager)
        try:
            if hasattr(obj, 'managed_department') and obj.managed_department: 
                departments.add(obj.managed_department.name)
        except Department.DoesNotExist:
            pass 
        
        # 3. Rəhbərlik etdiyi departament (Lead)
        try:
            if hasattr(obj, 'led_department') and obj.led_department: 
                departments.add(obj.led_department.name)
        except Department.DoesNotExist:
            pass

        # 4. Top menecment olaraq idarə etdikləri (M2M)
        if hasattr(obj, 'top_managed_departments'):
            for dept in obj.top_managed_departments.all(): 
                departments.add(dept.name)
                
        return list(departments)

    def validate_email(self, value):
        """
        E-poçt ünvanının unikal olmasını yoxlayır (həm create, həm update zamanı).
        """
        current_user = self.instance
        if current_user:
            # Update zamanı
            existing_user = User.objects.filter(email=value).exclude(pk=current_user.pk).first()
        else:
            # Create zamanı
            existing_user = User.objects.filter(email=value).first()
            
        if existing_user:
            raise serializers.ValidationError("Bu e-poçt ünvanı artıq istifadə olunur.")
        return value

    def create(self, validated_data):
        """
        Yeni istifadəçi yaradır və rola əsasən departament əlaqələrini təyin edir.
        """
        if 'username' not in validated_data:
            validated_data['username'] = validated_data.get('email')
        
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        
        role = validated_data.get('role')
        department = validated_data.get('department')

        # create_user metodu 'department' sahəsini (user.department) özü təyin edəcək
        user = User.objects.create_user(password=password, **validated_data)

        # Əgər rol manager/lead-dirsə, Department modelini də yeniləyirik
        if department:
            if role == 'manager':
                # Bu departamentin köhnə menecerini təmizləyib, yenisini təyin edirik
                Department.objects.filter(id=department.id).update(manager=user)
            elif role == 'department_lead':
                # Bu departamentin köhnə rəhbərini təmizləyib, yenisini təyin edirik
                Department.objects.filter(id=department.id).update(department_lead=user)

        if top_departments is not None:
            user.top_managed_departments.set(top_departments)
        
        return user

    def update(self, instance, validated_data):
        """
        Mövcud istifadəçini yeniləyir və rol dəyişikliklərini Department modelinə əks etdirir.
        """
        top_departments = validated_data.pop('top_managed_departments', None)
        password = validated_data.pop('password', None)
        profile_photo = validated_data.get('profile_photo')

        new_role = validated_data.get('role', instance.role)
        new_department = validated_data.get('department', instance.department)

        # --- Köhnə əlaqələri təmizləyirik ---
        # 1. Əgər rol "menecer"-dən dəyişirsə
        if 'role' in validated_data and instance.role == 'manager' and new_role != 'manager':
            Department.objects.filter(manager=instance).update(manager=None)

        # 2. Əgər rol "rəhbər"-dən dəyişirsə
        if 'role' in validated_data and instance.role == 'department_lead' and new_role != 'department_lead':
            Department.objects.filter(department_lead=instance).update(department_lead=None)
        
        # --- Profil şəklini təmizləmə ---
        if profile_photo == '':
            instance.profile_photo.delete(save=False)
            validated_data['profile_photo'] = None

        # --- User obyektini yeniləyirik ---
        instance = super().update(instance, validated_data)

        # --- Şifrəni yeniləyirik ---
        if password:
            instance.set_password(password)
        
        instance.save()

        # --- Yeni əlaqələri təyin edirik ---
        if new_department:
            if new_role == 'manager':
                # Bu istifadəçinin idarə etdiyi başqa departamenti təmizlə
                Department.objects.filter(manager=instance).exclude(id=new_department.id).update(manager=None)
                # Yeni departamentə menecer təyin et
                new_department.manager = instance
                new_department.save()
            
            elif new_role == 'department_lead':
                # Bu istifadəçinin rəhbərlik etdiyi başqa departamenti təmizlə
                Department.objects.filter(department_lead=instance).exclude(id=new_department.id).update(department_lead=None)
                # Yeni departamentə rəhbər təyin et
                new_department.department_lead = instance
                new_department.save()

        if top_departments is not None:
            instance.top_managed_departments.set(top_departments)
        
        return instance


class DepartmentSerializer(serializers.ModelSerializer):
    """
    Departament modeli üçün serializer.
    """
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
        fields = ['id', 'name', 'manager', 'department_lead', 'top_management']

    def update(self, instance, validated_data):
        """
        Update zamanı OneToOne əlaqələrinin unikal olmasını təmin edir.
        """
        new_lead = validated_data.get('department_lead')
        if new_lead:
            # Bu rəhbəri başqa departamentdən çıxar
            Department.objects.filter(department_lead=new_lead).exclude(pk=instance.pk).update(department_lead=None)
        
        new_manager = validated_data.get('manager')
        if new_manager:
            # Bu meneceri başqa departamentdən çıxar
            Department.objects.filter(manager=new_manager).exclude(pk=instance.pk).update(manager=None)

        return super().update(instance, validated_data)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login üçün istifadə olunan, E-poçt ilə işləyən xüsusi token serializer.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            # E-poçta görə istifadəçini tapırıq
            user = User.objects.filter(email=email).first()
            if not user:
                raise serializers.ValidationError("Bu email ilə istifadəçi tapılmadı.")
        except Exception:
            raise serializers.ValidationError("Bu email ilə istifadəçi tapılmadı.")

        if not user.check_password(password):
            raise serializers.ValidationError("Şifrə yanlışdır.")

        if not user.is_active:
            raise serializers.ValidationError("İstifadəçi aktiv deyil.")
            
        # Əsas validasiyanı `username` ilə davam etdiririk
        data = super().validate(attrs={self.username_field: user.get_username(), "password": password})

        # Cavaba istifadəçi məlumatlarını əlavə edirik
        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data

    def __init__(self, *args, **kwargs):
        # Serializer-i `username` yerinə `email` qəbul etməsi üçün dəyişdiririk
        super().__init__(*args, **kwargs)
        self.fields.pop(self.username_field, None)
        self.fields['email'] = serializers.EmailField()
        self.fields['password'] = serializers.CharField(write_only=True)