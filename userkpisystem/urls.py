from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserEvaluationViewSet

router = DefaultRouter()
router.register(r'user-evaluations', UserEvaluationViewSet, basename='userevaluation')

urlpatterns = [
    path("", include(router.urls)),
]