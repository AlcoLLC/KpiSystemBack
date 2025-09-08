from django.contrib import admin
from django.urls import path, include

from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, DepartmentViewSet, MyTokenObtainPairView, LogoutView, ProfileViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet)
router.register(r"departments", DepartmentViewSet)
router.register(r'profiles', ProfileViewSet, basename='profile') 

urlpatterns = [
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("", include(router.urls)),
]

