"""
URL configuration for the products app.
"""
from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Changed from 'setup' to 'product_setup' to match template
    path('', views.product_setup, name='product_setup'),
    path('ajax/load-models/', views.ajax_load_models, name='ajax_load_models'),
]