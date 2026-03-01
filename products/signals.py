# products/signals.py  — FULL REPLACEMENT
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.cache import cache
from django.db import transaction
from .models import Product, ProductCategory, ProductPacking, ProductPriceHistory


@receiver(post_save, sender=Product)
def clear_product_cache(sender, instance, **kwargs):
    """Clear product cache when product is saved"""
    transaction.on_commit(lambda: cache.delete(f'product_{instance.id}'))
    transaction.on_commit(lambda: cache.delete('featured_products'))
    transaction.on_commit(lambda: cache.delete('products_list'))


@receiver(post_delete, sender=Product)
def clear_product_cache_on_delete(sender, instance, **kwargs):
    """Clear product cache when product is deleted"""
    transaction.on_commit(lambda: cache.delete(f'product_{instance.id}'))
    transaction.on_commit(lambda: cache.delete('featured_products'))
    transaction.on_commit(lambda: cache.delete('products_list'))


@receiver(post_save, sender=ProductCategory)
def clear_category_cache(sender, instance, **kwargs):
    """Clear category cache when category is saved"""
    transaction.on_commit(lambda: cache.delete('category_tree'))
    transaction.on_commit(lambda: cache.delete('categories_list'))


@receiver(post_save, sender=ProductPacking)
def update_product_pricing(sender, instance, **kwargs):
    """Update product price if this is the default packing"""
    if instance.is_default and instance.price:
        if instance.product.price != instance.price:
            def update_price():
                ProductPriceHistory.objects.create(
                    product=instance.product,
                    old_price=instance.product.price,
                    new_price=instance.price,
                    reason=f"Updated from packing: {instance.packing_unit.name}"
                )
                instance.product.price = instance.price
                instance.product.save(update_fields=['price'])

            transaction.on_commit(update_price)


@receiver(pre_save, sender=Product)
def track_price_change(sender, instance, **kwargs):
    """
    FIX D+E: Store old price on instance before save.
    The post_save handler below reads it and creates the history record.
    """
    if instance.pk:
        try:
            old_instance = Product.objects.get(pk=instance.pk)
            if old_instance.price != instance.price:
                instance._old_price = old_instance.price
                instance._old_currency = old_instance.currency
            else:
                instance._old_price = None
                instance._old_currency = None
        except Product.DoesNotExist:
            instance._old_price = None
            instance._old_currency = None
    else:
        instance._old_price = None
        instance._old_currency = None


@receiver(post_save, sender=Product)
def record_price_history(sender, instance, created, **kwargs):
    """
    FIX D+E: Create ProductPriceHistory after a price change.
    Reads _old_price set by the pre_save signal above.
    Only runs when a price change was detected (not on new product creation).
    """
    if created:
        return  # No history needed for brand new products

    old_price = getattr(instance, '_old_price', None)
    if old_price is None:
        return  # Price did not change

    old_currency = getattr(instance, '_old_currency', None)
    reason = "Price updated"
    if old_currency != instance.currency:
        old_code = old_currency.code if old_currency else "None"
        new_code = instance.currency.code if instance.currency else "None"
        reason += f" and currency changed from {old_code} to {new_code}"

    def create_history():
        ProductPriceHistory.objects.create(
            product=instance,
            old_price=old_price,
            new_price=instance.price,
            reason=reason
        )

    transaction.on_commit(create_history)