# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('ajax/load-regions/', views.ajax_load_regions, name='ajax_load_regions'),
    path('ajax/load-cities/', views.ajax_load_cities, name='ajax_load_cities'),
    path('ajax/load-cities-by-region/', views.ajax_load_cities_by_region, name='ajax_load_cities_by_region'),
]