from django.urls import path
from .views import SubordinateListView, PerformanceSummaryView

urlpatterns = [
    path('subordinates/', SubordinateListView.as_view(), name='subordinate-list'),
    path('summary/<slug:slug>/', PerformanceSummaryView.as_view(), name='performance-summary'),
]