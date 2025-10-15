from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ActivityLogViewSet, DashboardStatsView, UserListView

router = DefaultRouter()
router.register(r'activity-logs', ActivityLogViewSet, basename='activity-log')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('users/', UserListView.as_view(), name='user-list-for-filter'),
]