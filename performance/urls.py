from django.urls import path
from .views import SubordinateListView, PerformanceSummaryView, KpiMonthlySummaryView, FilterableDepartmentListView

urlpatterns = [
    path('subordinates/', SubordinateListView.as_view(), name='subordinate-list'),
    path('filterable-departments/', FilterableDepartmentListView.as_view(), name='filterable-department-list'),
    path('summary/me/', PerformanceSummaryView.as_view(), name='my-performance-summary'),
    path('summary/<slug:slug>/', PerformanceSummaryView.as_view(), name='performance-summary'),
    path('kpi-summary/<slug:slug>/', KpiMonthlySummaryView.as_view(), name='kpi-monthly-summary'),

]