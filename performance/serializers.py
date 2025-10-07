from rest_framework import serializers
from accounts.models import User

class SubordinateSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='get_role_display', read_only=True)
    department = serializers.CharField(source='department.name', read_only=True)
    full_name = serializers.SerializerMethodField()
    
    # YENİ ƏLAVƏ OLUNAN SAHƏ
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'slug', 'profile_photo', 'full_name', 'role', 'department', 'email']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username
        
    # YENİ ƏLAVƏ OLUNAN METOD
    def get_profile_photo(self, obj):
        request = self.context.get('request', None)
        if obj.profile_photo and hasattr(obj.profile_photo, 'url'):
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None
