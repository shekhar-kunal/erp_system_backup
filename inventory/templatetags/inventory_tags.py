# inventory/templatetags/inventory_tags.py
from django import template
from ..models import InventorySettings

register = template.Library()

@register.simple_tag
def inventory_feature_enabled(feature_name):
    """Template tag to check if a feature is enabled"""
    settings = InventorySettings.get_settings()
    return getattr(settings, f'enable_{feature_name}', False)