from django.urls import path
from . import views

urlpatterns = [
    path('', views.erp_setup_wizard, name='erp_setup'),
]