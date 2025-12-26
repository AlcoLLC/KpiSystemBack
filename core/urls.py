from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/kpis/', include('kpis.urls')),
    path('api/tasks/', include('tasks.urls')),
    path('api/performance/', include('performance.urls')),
    path('api/performance/', include('userkpisystem.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/equipment/', include('equipment.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else settings.STATIC_ROOT)
