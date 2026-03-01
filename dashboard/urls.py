from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_home, name='dashboard'),
    path('global/', views.global_dashboard, name='dashboard-global'),
    path('sales/', views.sales_dashboard, name='dashboard-sales'),
    path('inventory/', views.inventory_dashboard, name='dashboard-inventory'),
    path('purchasing/', views.purchasing_dashboard, name='dashboard-purchasing'),
    path('finance/', views.finance_dashboard, name='dashboard-finance'),
    path('warehouse/', views.warehouse_dashboard, name='dashboard-warehouse'),
]
