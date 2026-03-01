from django.db.models import Count, Sum, Q
from datetime import timedelta
from django.utils import timezone
from .models import Vendor, PurchaseOrder


class PurchasingDashboard:
    """Dashboard metrics for Purchasing module"""
    
    @classmethod
    def get_metrics(cls):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        return {
            'total_vendors': Vendor.objects.filter(is_active=True).count(),
            'active_pos': PurchaseOrder.objects.filter(
                status__in=['confirmed', 'partial']
            ).count(),
            'pending_receipts': PurchaseOrder.objects.filter(
                status='confirmed',
                expected_date__lte=today
            ).count(),
            'monthly_purchases': PurchaseOrder.objects.filter(
                order_date__gte=month_ago,
                status='done'
            ).aggregate(
                total=Sum('total_amount')
            )['total'] or 0,
            'top_vendors': Vendor.objects.annotate(
                purchase_total=Sum('purchase_orders__total_amount', 
                                 filter=Q(purchase_orders__status='done'))
            ).filter(purchase_total__gt=0).order_by('-purchase_total')[:5],
            'recent_orders': PurchaseOrder.objects.select_related(
                'vendor', 'warehouse'
            ).order_by('-order_date')[:10]
        }