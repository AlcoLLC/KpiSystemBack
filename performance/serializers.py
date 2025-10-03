from rest_framework import serializers
from accounts.models import User

class SubordinateSerializer(serializers.ModelSerializer):
    """İşçilərin siyahısı üçün yüngül serializer."""
    role = serializers.CharField(source='get_role_display', read_only=True)
    department = serializers.CharField(source='department.name', read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'slug', 'profile_photo', 'full_name', 'role', 'department', 'email']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username