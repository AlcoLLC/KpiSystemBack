from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DepartmentViewSet, EmployeeViewSet, KPIEvaluationViewSet

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet)
router.register(r"employees", EmployeeViewSet)
router.register(r"kpi", KPIEvaluationViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
