from rest_framework import viewsets, generics, status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as rest_filters
from .models import Equipment, EquipmentVolume, DailyProduction
from .serializers import (
    EquipmentSerializer, 
    EquipmentVolumeSerializer, 
    DailyProductionSerializer, 
    UserShortSerializer
)
from django.contrib.auth import get_user_model
from .filters import EquipmentFilter, EquipmentVolumeFilter, DailyProductionFilter
from rest_framework.response import Response

User = get_user_model()


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = EquipmentFilter
    search_fields = ['name']


class EquipmentVolumeViewSet(viewsets.ModelViewSet):
    queryset = EquipmentVolume.objects.all()
    serializer_class = EquipmentVolumeSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = EquipmentVolumeFilter
    search_fields = ['volume', 'equipment__name']


class DailyProductionViewSet(viewsets.ModelViewSet):
    queryset = DailyProduction.objects.all()
    serializer_class = DailyProductionSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = DailyProductionFilter
    search_fields = ['equipment__name', 'note']

    def get_queryset(self):
        """
        Factory hierarchy əsasında queryset qaytarır.
        Filter class-ında da əlavə filtrasiya var.
        """
        return DailyProduction.objects.all().select_related(
            'equipment'
        ).prefetch_related(
            'employees', 'items__volume'
        ).order_by('-date', '-id')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class FactoryEmployeeListView(generics.ListAPIView):
    """
    Factory hierarchy əsasında işçi siyahısı.
    Hər istifadəçi yalnız öz səlahiyyəti daxilindəki işçiləri görür.
    """
    serializer_class = UserShortSerializer

    def get_queryset(self):
        user = self.request.user
        
        # Admin bütün factory işçilərini görür
        if user.role == 'admin':
            return User.objects.filter(
                factory_type__in=['dolum', 'bidon'], 
                is_active=True
            ).order_by('first_name', 'last_name')
        
        # Factory istifadəçisi deyilsə heç kim göstərmə
        if not user.factory_role or not user.factory_type:
            return User.objects.none()
        
        # Base queryset - eyni factory_type
        queryset = User.objects.filter(
            factory_type=user.factory_type,
            is_active=True
        )
        
        if user.factory_role == 'top_management':
            return queryset.exclude(id=user.id).order_by('first_name', 'last_name')
        
        elif user.factory_role == 'deputy_director':
            return queryset.filter(
                factory_role__in=['department_lead', 'employee']
            ).order_by('first_name', 'last_name')
        
        elif user.factory_role == 'department_lead':
            return queryset.filter(
                factory_role='employee'
            ).order_by('first_name', 'last_name')
        
        elif user.factory_role == 'employee':
            return queryset.filter(id=user.id)
        
        return User.objects.none()