# inventory/dashboard.py
from django.db import models
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from .models import Warehouse, Stock, StockMovement, StockBatch


class InventoryDashboard:
    """Dashboard metrics for Inventory module"""
    
    @classmethod
    def get_metrics(cls):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Warehouse metrics
        total_warehouses = Warehouse.objects.filter(is_active=True).count()
        
        # Stock metrics
        total_products_in_stock = Stock.objects.filter(quantity__gt=0).count()
        low_stock_items = Stock.objects.filter(
            quantity__lte=models.F('reorder_level')
        ).count()
        
        # Movement metrics
        recent_movements = StockMovement.objects.filter(
            created_at__date__gte=week_ago
        ).count()
        
        # Batch metrics
        expiring_batches = StockBatch.objects.filter(
            expiry_date__lte=today + timedelta(days=30),
            expiry_date__gt=today,
            is_active=True
        ).count()
        
        expired_batches = StockBatch.objects.filter(
            expiry_date__lt=today,
            is_active=True
        ).count()
        
        # Total stock value
        total_value = Stock.objects.aggregate(
            total=Sum(models.F('quantity') * models.F('product__cost'))
        )['total'] or 0
        
        return {
            'total_warehouses': total_warehouses,
            'total_products_in_stock': total_products_in_stock,
            'low_stock_items': low_stock_items,
            'recent_movements': recent_movements,
            'expiring_batches': expiring_batches,
            'expired_batches': expired_batches,
            'total_value': total_value,
        }