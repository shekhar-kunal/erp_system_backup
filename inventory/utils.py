# inventory/utils.py
from decimal import Decimal
from datetime import datetime, timedelta, date
from django.db import transaction
from django.db.models import Sum, F, Q, Count, Avg
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Stock, StockMovement, Warehouse, StockCount, StockBatch, InventorySettings
import logging

logger = logging.getLogger(__name__)


class InventoryManager:
    """Advanced inventory management utilities"""
    
    @staticmethod
    @transaction.atomic
    def transfer_stock(product, source_warehouse, target_warehouse, qty, 
                       section_from=None, section_to=None, user=None, reference=""):
        """
        Transfer stock from one warehouse/section to another safely.
        Returns the created movements.
        """
        if qty <= 0:
            raise ValueError("Transfer quantity must be positive")

        # Get source stock
        source_stock = Stock.objects.filter(
            product=product,
            warehouse=source_warehouse,
            section=section_from
        ).first()
        
        if not source_stock or source_stock.quantity < qty:
            raise ValueError(
                f"Not enough stock in {source_warehouse.name}. "
                f"Available: {source_stock.quantity if source_stock else 0}, requested: {qty}"
            )

        # Get or create target stock
        target_stock, _ = Stock.objects.get_or_create(
            product=product,
            warehouse=target_warehouse,
            section=section_to,
            defaults={
                'quantity': 0,
                'unit': source_stock.unit,
                'unit_quantity': source_stock.unit_quantity,
                'reorder_level': source_stock.reorder_level
            }
        )

        # Remove from source
        source_movement = source_stock.remove_stock(
            qty=qty,
            reference=reference or f"Transfer to {target_warehouse.name}",
            source="transfer",
            notes=f"Transfer OUT to {target_warehouse.name}",
            user=user
        )

        # Add to target
        target_movement = target_stock.add_stock(
            qty=qty,
            reference=reference or f"Transfer from {source_warehouse.name}",
            source="transfer",
            notes=f"Transfer IN from {source_warehouse.name}",
            unit_qty=source_stock.unit_quantity,
            user=user
        )

        return {
            'source_movement': source_movement,
            'target_movement': target_movement,
            'source_stock': source_stock,
            'target_stock': target_stock
        }

    @staticmethod
    def get_inventory_valuation(warehouse=None, category=None):
        """
        Calculate inventory valuation with optional filters
        Returns total value and breakdown
        """
        stocks = Stock.objects.select_related('product', 'warehouse').all()
        
        if warehouse:
            stocks = stocks.filter(warehouse=warehouse)
        if category:
            stocks = stocks.filter(product__category=category)
        
        total_value = Decimal('0')
        valuation_by_warehouse = {}
        valuation_by_category = {}
        
        for stock in stocks:
            value = stock.total_value
            total_value += value
            
            # By warehouse
            wh_name = stock.warehouse.name
            valuation_by_warehouse[wh_name] = valuation_by_warehouse.get(wh_name, 0) + value
            
            # By category
            if stock.product.category:
                cat_name = stock.product.category.name
                valuation_by_category[cat_name] = valuation_by_category.get(cat_name, 0) + value
        
        return {
            'total_value': total_value,
            'by_warehouse': valuation_by_warehouse,
            'by_category': valuation_by_category,
            'total_items': stocks.count()
        }

    @staticmethod
    def get_movement_analysis(days=30):
        """
        Analyze stock movements over specified period
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        movements = StockMovement.objects.filter(
            created_at__gte=cutoff_date
        ).select_related('product', 'warehouse')
        
        analysis = {
            'total_in': movements.filter(movement_type='IN').aggregate(
                total=Sum('quantity')
            )['total'] or 0,
            'total_out': movements.filter(movement_type='OUT').aggregate(
                total=Sum('quantity')
            )['total'] or 0,
            'by_product': {},
            'by_warehouse': {}
        }
        
        # Movement by product
        product_movements = movements.values('product__name').annotate(
            total_in=Sum('quantity', filter=Q(movement_type='IN')),
            total_out=Sum('quantity', filter=Q(movement_type='OUT')),
            count=Count('id')
        )
        
        for pm in product_movements:
            analysis['by_product'][pm['product__name']] = pm
        
        # Movement by warehouse
        warehouse_movements = movements.values('warehouse__name').annotate(
            total=Sum('quantity'),
            count=Count('id')
        )
        
        for wm in warehouse_movements:
            analysis['by_warehouse'][wm['warehouse__name']] = wm
        
        return analysis

    @staticmethod
    def get_reorder_report():
        """Generate report of items needing reorder"""
        low_stock = Stock.objects.filter(
            quantity__lte=F('reorder_level')
        ).select_related('product', 'warehouse')
        
        report = []
        for stock in low_stock:
            report.append({
                'product': stock.product.name,
                'sku': stock.product.sku,
                'warehouse': stock.warehouse.name,
                'current_qty': stock.quantity,
                'reorder_level': stock.reorder_level,
                'recommended_order': max(
                    stock.reorder_level * 2 - stock.quantity,
                    stock.reorder_level
                ),
                'unit': stock.unit.code if stock.unit else 'base',
                'value': stock.total_value
            })
        
        return report

    @staticmethod
    def send_reorder_alerts():
        """Send email alerts for items needing reorder"""
        settings = InventorySettings.get_settings()
        if not settings.enable_auto_reorder:
            logger.info("Auto reorder alerts are disabled")
            return False
        
        report = InventoryManager.get_reorder_report()
        
        if report:
            subject = f"Reorder Alert - {date.today()}"
            message = "ITEMS NEEDING REORDER:\n\n"
            
            for item in report:
                message += f"- {item['product']} ({item['sku']}) @ {item['warehouse']}\n"
                message += f"  Current: {item['current_qty']} {item['unit']}, Reorder at: {item['reorder_level']}\n"
                message += f"  Recommended: {item['recommended_order']} units\n\n"
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                getattr(settings, 'INVENTORY_ALERT_EMAILS', []),
                fail_silently=True
            )
            logger.info(f"Reorder alert sent for {len(report)} items")
            return True
        
        return False

    @staticmethod
    def get_expiring_batches(days=30):
        """Get batches expiring within specified days"""
        from datetime import date, timedelta
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            return StockBatch.objects.none()
        
        target_date = date.today() + timedelta(days=days)
        
        return StockBatch.objects.filter(
            expiry_date__lte=target_date,
            expiry_date__gte=date.today(),
            quantity__gt=0,
            is_active=True
        ).select_related('stock__product', 'stock__warehouse')

    @staticmethod
    def get_expired_batches():
        """Get all expired batches"""
        from datetime import date
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            return StockBatch.objects.none()
        
        return StockBatch.objects.filter(
            expiry_date__lt=date.today(),
            quantity__gt=0
        ).select_related('stock__product', 'stock__warehouse')

    @staticmethod
    def send_expiry_alerts():
        """Send email alerts for expiring batches"""
        from datetime import date
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            logger.info("Batch tracking is disabled")
            return False
        
        expiring_30 = InventoryManager.get_expiring_batches(30)
        expiring_7 = InventoryManager.get_expiring_batches(7)
        expired = InventoryManager.get_expired_batches()
        
        if expiring_30.exists() or expired.exists():
            subject = f"Stock Expiry Alert - {date.today()}"
            message = "EXPIRY REPORT\n" + "="*50 + "\n\n"
            
            if expired.exists():
                message += "EXPIRED BATCHES:\n"
                for batch in expired:
                    message += f"- {batch.batch_number}: {batch.stock.product.name} ({abs(batch.days_to_expiry)} days expired)\n"
            
            if expiring_7.exists():
                message += "\nEXPIRING IN 7 DAYS:\n"
                for batch in expiring_7:
                    message += f"- {batch.batch_number}: {batch.stock.product.name} (expires {batch.expiry_date})\n"
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                getattr(settings, 'INVENTORY_ALERT_EMAILS', []),
                fail_silently=True
            )
            logger.info(f"Expiry alert sent")
            return True
        
        return False


class InventoryValuation:
    """Calculate inventory value using different methods"""
    
    def __init__(self, stock_queryset=None):
        self.stock = stock_queryset or Stock.objects.all()
        self.settings = InventorySettings.get_settings()
    
    def calculate_value(self, method=None):
        """Calculate inventory value using specified method"""
        method = method or self.settings.valuation_method
        
        if method == 'fifo':
            return self._fifo_valuation()
        elif method == 'lifo':
            return self._lifo_valuation()
        elif method == 'average':
            return self._average_valuation()
        elif method == 'standard':
            return self._standard_valuation()
        else:
            return self._standard_valuation()
    
    def _fifo_valuation(self):
        """FIFO valuation using batch costs"""
        total = Decimal('0')
        for stock in self.stock.prefetch_related('batches'):
            if not self.settings.enable_batch_tracking:
                total += stock.total_value
            else:
                for batch in stock.batches.filter(is_active=True).order_by('received_date'):
                    # Assuming you add unit_cost to batch model later
                    batch_cost = batch.quantity * (getattr(batch, 'unit_cost', None) or stock.product.cost_price or 0)
                    total += batch_cost
        return total
    
    def _lifo_valuation(self):
        """LIFO valuation using latest batch costs"""
        total = Decimal('0')
        for stock in self.stock.prefetch_related('batches'):
            if not self.settings.enable_batch_tracking:
                total += stock.total_value
            else:
                for batch in stock.batches.filter(is_active=True).order_by('-received_date'):
                    batch_cost = batch.quantity * (getattr(batch, 'unit_cost', None) or stock.product.cost_price or 0)
                    total += batch_cost
        return total
    
    def _average_valuation(self):
        """Weighted average cost valuation"""
        total = Decimal('0')
        for stock in self.stock:
            avg_cost = self._calculate_average_cost(stock)
            total += stock.quantity * avg_cost
        return total
    
    def _standard_valuation(self):
        """Standard cost valuation (uses product cost_price)"""
        total = Decimal('0')
        for stock in self.stock:
            total += stock.total_value
        return total
    
    def _calculate_average_cost(self, stock):
        """Calculate weighted average cost for a stock item"""
        if not self.settings.enable_batch_tracking:
            return stock.product.cost_price or 0
        
        total_cost = Decimal('0')
        total_qty = Decimal('0')
        
        for batch in stock.batches.filter(is_active=True):
            batch_cost = batch.quantity * (getattr(batch, 'unit_cost', None) or stock.product.cost_price or 0)
            total_cost += batch_cost
            total_qty += batch.quantity
        
        if total_qty > 0:
            return total_cost / total_qty
        return stock.product.cost_price or 0


# Performance monitoring decorator
def monitor_performance(func):
    """Decorator to monitor function performance"""
    def wrapper(*args, **kwargs):
        import time
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        logger.info(f"{func.__name__} took {duration:.2f} seconds")
        
        if duration > 5:
            logger.warning(f"SLOW OPERATION: {func.__name__} took {duration:.2f} seconds")
        
        return result
    return wrapper


@monitor_performance
def run_inventory_audit():
    """Run a complete inventory audit"""
    manager = InventoryManager()
    
    # Get valuation
    valuation = manager.get_inventory_valuation()
    print(f"Total Inventory Value: ${valuation['total_value']:,.2f}")
    
    # Analyze movements
    analysis = manager.get_movement_analysis(days=30)
    print(f"30-day Movement: IN={analysis['total_in']}, OUT={analysis['total_out']}")
    
    # Generate reorder report
    report = manager.get_reorder_report()
    print(f"Low Stock Items: {len(report)}")
    
    return {
        'valuation': valuation,
        'analysis': analysis,
        'reorder_report': report
    }