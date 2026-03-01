"""URL patterns for the Reports & Analytics app."""
from django.urls import path
from . import views

urlpatterns = [
    path('',                     views.report_index,        name='reports-index'),
    path('inventory-valuation/', views.inventory_valuation, name='report-inventory-valuation'),
    path('stock-aging/',         views.stock_aging,         name='report-stock-aging'),
    path('low-stock/',           views.low_stock,           name='report-low-stock'),
    path('sales/',               views.sales_report,        name='report-sales'),
    path('customer-sales/',      views.customer_sales,      name='report-customer-sales'),
    path('top-products/',        views.top_products,        name='report-top-products'),
    path('purchases/',           views.purchase_report,     name='report-purchases'),
    path('supplier/',            views.supplier_report,     name='report-supplier'),
    path('warehouse-movement/',  views.warehouse_movement,  name='report-warehouse-movement'),
    path('profit/',              views.profit_analysis,     name='report-profit'),
    path('ar-aging/',            views.ar_aging,            name='report-ar-aging'),
    path('ap-aging/',            views.ap_aging,            name='report-ap-aging'),
    path('tax/',                 views.tax_report,          name='report-tax'),
    path('custom/',              views.custom_builder,      name='report-custom'),
]
