"""
URL configuration for the products app.
"""
from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.product_setup, name='product_setup'),
    path('ajax/load-models/',   views.ajax_load_models,   name='ajax_load_models'),
    path('ajax/product-info/',  views.ajax_product_info,  name='ajax_product_info'),
]