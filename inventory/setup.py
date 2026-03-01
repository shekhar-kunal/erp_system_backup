# inventory/setup.py
from .models import InventorySettings

def setup_inventory_settings():
    """Create default settings during installation"""
    settings, created = InventorySettings.objects.get_or_create(pk=1)
    if created:
        settings.enable_batch_tracking = True
        settings.enable_auto_reorder = True
        settings.valuation_method = 'fifo'
        settings.save()
    return settings