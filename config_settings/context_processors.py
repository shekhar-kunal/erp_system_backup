from .models import ERPSettings
from .models import Currency

def erp_settings(request):
    """
    Context processor to add ERP settings status to all templates.
    This makes 'erp_settings_configured' available in every template context.
    """
    return {
        'erp_settings_configured': ERPSettings.objects.exists()
    }


def currencies(request):
    """Make currencies available to all templates"""
    return {
        'currencies': Currency.objects.filter(is_active=True),
        'base_currency': Currency.objects.filter(is_base=True).first(),
    }