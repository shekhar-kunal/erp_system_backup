# inventory/signals.py
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Stock, StockMovement, Warehouse
from products.models import Product


@receiver(post_save, sender=StockMovement)
def update_stock_last_movement(sender, instance, created, **kwargs):
    """Update stock last_movement timestamp"""
    if created:
        try:
            stock = Stock.objects.get(
                product=instance.product,
                warehouse=instance.warehouse,
                section=instance.section
            )
            stock.last_movement = instance.created_at
            stock.save(update_fields=['last_movement'])
        except Stock.DoesNotExist:
            pass


@receiver(post_save, sender=Stock)
def check_low_stock_alert(sender, instance, created, **kwargs):
    """Send alert when stock goes below reorder level"""
    if not created and instance.quantity <= instance.reorder_level:
        # Check if this is a new low stock condition
        try:
            old_instance = Stock.objects.get(pk=instance.pk)
            if old_instance.quantity > instance.reorder_level:
                # Send email alert
                subject = f'Low Stock Alert: {instance.product.name}'
                message = f"""
                Product: {instance.product.name}
                SKU: {instance.product.sku}
                Warehouse: {instance.warehouse.name}
                Current Stock: {instance.quantity}
                Reorder Level: {instance.reorder_level}
                
                Please reorder soon!
                """
                
                # Send to warehouse manager and purchasing team
                recipients = []
                if instance.warehouse.manager and instance.warehouse.manager.email:
                    recipients.append(instance.warehouse.manager.email)
                
                # Add default alert recipients from settings
                recipients.extend(getattr(settings, 'INVENTORY_ALERT_EMAILS', []))
                
                if recipients:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        recipients,
                        fail_silently=True
                    )
        except Stock.DoesNotExist:
            pass


@receiver(post_save, sender=Stock)
def update_warehouse_section_occupancy(sender, instance, **kwargs):
    """Update section occupancy when stock changes"""
    if instance.section:
        # Use delay to avoid recursion
        from django.db.models.signals import post_save
        post_save.disconnect(update_warehouse_section_occupancy, sender=Stock)
        instance.section.update_occupancy()
        post_save.connect(update_warehouse_section_occupancy, sender=Stock)


@receiver(post_save, sender=Warehouse)
def check_warehouse_capacity(sender, instance, **kwargs):
    """Alert when warehouse capacity is exceeded"""
    if instance.capacity and instance.current_utilization() > instance.utilization_threshold:
        subject = f'Warehouse Capacity Alert: {instance.name}'
        message = f"""
        Warehouse: {instance.name}
        Current Utilization: {instance.current_utilization():.1f}%
        Threshold: {instance.utilization_threshold}%
        Capacity: {instance.capacity}
        
        Please review warehouse utilization!
        """
        
        recipients = []
        if instance.manager and instance.manager.email:
            recipients.append(instance.manager.email)
        
        if recipients:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True
            )


# Auto-create stock records when products are created (optional)
@receiver(post_save, sender='products.Product')
def create_initial_stock(sender, instance, created, **kwargs):
    """Create initial stock records for new products in main warehouse"""
    if created:
        main_warehouses = Warehouse.objects.filter(warehouse_type='main', is_active=True)
        for warehouse in main_warehouses:
            Stock.objects.get_or_create(
                product=instance,
                warehouse=warehouse,
                defaults={'quantity': 0}
            )


# Auto-create StockCount from CSV import
def import_stock_count_from_csv(file_path, warehouse_id, count_name, user):
    """Utility to import stock count from CSV"""
    import csv
    from .models import StockCount, StockCountLine
    
    stock_count = StockCount.objects.create(
        name=count_name,
        warehouse_id=warehouse_id,
        created_by=user,
        status='draft'
    )
    
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            product = Product.objects.get(sku=row['sku'])
            StockCountLine.objects.create(
                stock_count=stock_count,
                product=product,
                expected_quantity=float(row.get('expected', 0)),
                counted_quantity=float(row.get('counted', 0)) if row.get('counted') else None
            )
    
    return stock_count