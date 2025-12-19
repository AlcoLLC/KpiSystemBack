from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, 
    MyTokenObtainPairView, 
    LogoutView, 
    PositionViewSet,
    FactoryStatsView
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename='user')
router.register(r"positions", PositionViewSet, basename='position')

urlpatterns = [
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    path('factory-stats/', FactoryStatsView.as_view(), name='factory-stats'),
    
    path("", include(router.urls)),
]