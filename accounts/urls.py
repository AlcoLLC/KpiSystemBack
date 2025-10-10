from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, DepartmentViewSet, MyTokenObtainPairView, LogoutView, UserProfileView, FilterableDepartmentListView, PositionViewSet, AvailableDepartmentsForRoleView

router = DefaultRouter()
router.register(r"users", UserViewSet)
router.register(r"departments", DepartmentViewSet)
router.register(r"positions", PositionViewSet, basename='position')

urlpatterns = [
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
    path('filterable-departments/', FilterableDepartmentListView.as_view(), name='filterable-departments'),
    path('available-departments/', AvailableDepartmentsForRoleView.as_view(), name='available-departments'),
    path("", include(router.urls)),

]