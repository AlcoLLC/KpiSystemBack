from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, TaskVerificationView, AssignableUserListView, MonthlyTaskStatsView, PriorityTaskStatsView, HomeStatsView

router = DefaultRouter()

router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
    path('tasks/verify/<str:token>/', TaskVerificationView.as_view(), name='task-verify'),
    path('assignable-users/', AssignableUserListView.as_view(), name='assignable-user-list'),
    path('stats/monthly/', MonthlyTaskStatsView.as_view(), name='monthly-task-stats'),
    path('stats/priority/', PriorityTaskStatsView.as_view(), name='priority-task-stats'),
    path('home-stats/', HomeStatsView.as_view(), name='task_home_stats'),

]
