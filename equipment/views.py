from rest_framework import viewsets, generics, status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as rest_filters
from .models import Equipment, EquipmentVolume, DailyProduction
from .serializers import EquipmentSerializer, EquipmentVolumeSerializer, DailyProductionSerializer, UserShortSerializer
from django.contrib.auth import get_user_model
from .filters import EquipmentFilter, EquipmentVolumeFilter, DailyProductionFilter
from rest_framework.response import Response

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

User = get_user_model()

class DailyProductionViewSet(viewsets.ModelViewSet):
    queryset = DailyProduction.objects.all().order_by('-date', '-id')
    serializer_class = DailyProductionSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = DailyProductionFilter
    search_fields = ['equipment__name']

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
    serializer_class = UserShortSerializer

    def get_queryset(self):
        return User.objects.filter(
            factory_type__in=['dolum', 'bidon'], 
            is_active=True
        ).order_by('first_name', 'last_name')