from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('predictor.urls')),  # Then '/forecast/' is defined in predictor/urls.py
]
