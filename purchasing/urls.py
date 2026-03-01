from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    VendorViewSet, PurchaseOrderViewSet, PurchaseReceiptViewSet,
    purchasing_dashboard, purchase_summary_report, vendor_performance_report
)
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


# Create router for API endpoints
router = DefaultRouter()
router.register(r'vendors', VendorViewSet, basename='vendor')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchaseorder')
router.register(r'purchase-receipts', PurchaseReceiptViewSet, basename='purchasereceipt')

app_name = 'purchasing'

urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),
    
    # Dashboard
    path('dashboard/', purchasing_dashboard, name='dashboard'),
    
    # Reports
    path('reports/purchase-summary/', purchase_summary_report, name='purchase_summary'),
    path('reports/vendor-performance/', vendor_performance_report, name='vendor_performance'),
    
    # Additional API endpoints if needed
    path('api/purchase-orders/<int:pk>/confirm/', 
         views.confirm_purchase_order, name='confirm-purchase-order'),
    path('api/purchase-orders/<int:pk>/cancel/', 
         views.cancel_purchase_order, name='cancel-purchase-order'),
    path('api/purchase-orders/<int:pk>/receive/', 
         views.receive_purchase_order, name='receive-purchase-order'),
]


def send_overdue_notification(po):
    """Send email notification for overdue PO"""
    subject = f'Purchase Order {po.po_number} is Overdue'
    html_message = render_to_string('emails/overdue_po.html', {'po': po})
    send_mail(
        subject,
        '',
        settings.DEFAULT_FROM_EMAIL,
        [po.created_by.email] if po.created_by else [],
        html_message=html_message,
        fail_silently=True,
    )