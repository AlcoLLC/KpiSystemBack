from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, TaskVerificationView, AssignableUserListView

router = DefaultRouter()

router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
    path('tasks/verify/<str:token>/', TaskVerificationView.as_view(), name='task-verify'),
    path('assignable-users/', AssignableUserListView.as_view(), name='assignable-user-list'),
]