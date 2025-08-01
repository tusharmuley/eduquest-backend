from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('bookapp.urls')),
    path('auth_api/', include('auth_api.urls')),
]
