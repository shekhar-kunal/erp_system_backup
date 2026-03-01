from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderHistory


@receiver(pre_save, sender=PurchaseOrder)
def track_purchase_order_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = PurchaseOrder.objects.get(pk=instance.pk)
            if old.status != instance.status:
                # Log status change
                PurchaseOrderHistory.objects.create(
                    purchase_order=instance,
                    # get_current_user would need to be implemented via middleware
                    # changed_by=get_current_user(),
                    action='status_change',
                    field_name='status',
                    old_value=old.status,
                    new_value=instance.status
                )
        except PurchaseOrder.DoesNotExist:
            pass


@receiver(post_save, sender=PurchaseOrderLine)
def update_order_totals(sender, instance, **kwargs):
    """Update PO totals when line changes"""
    instance.order.calculate_totals()
    instance.order.save(update_fields=['subtotal', 'total_amount'])