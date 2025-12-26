from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyProductionViewSet, EquipmentViewSet, EquipmentVolumeViewSet, FactoryEmployeeListView

router = DefaultRouter()
router.register(r'equipments', EquipmentViewSet)
router.register(r'volumes', EquipmentVolumeViewSet)
router.register(r'productions', DailyProductionViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('factory-employees/', FactoryEmployeeListView.as_view(), name='factory-employees'),
]