from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .models import ERPSettings, ModuleStatus, PricingConfig
from products.models import PriceList

@staff_member_required
def erp_setup_wizard(request):
    """Global ERP setup wizard - first time configuration"""
    
    settings = ERPSettings.get_settings()
    
    # If setup is already completed, redirect to admin
    if settings.setup_completed:
        messages.info(request, "ERP setup is already completed. You can view settings in the admin.")
        return redirect('admin:index')
    
    if request.method == 'POST':
        # Save settings from wizard
        settings.price_decimals = int(request.POST.get('price_decimals', 4))
        settings.cost_decimals = int(request.POST.get('cost_decimals', 4))
        settings.default_currency = request.POST.get('currency', 'USD')
        settings.currency_position = request.POST.get('currency_position', 'before')
        settings.thousand_separator = request.POST.get('thousand_separator', 'comma')
        settings.sku_pattern = request.POST.get('sku_pattern', '{CATEGORY}-{SEQUENCE}')
        settings.sku_length = int(request.POST.get('sku_length', 8))
        settings.company_name = request.POST.get('company_name', '')
        settings.save()
        
        # Save pricing configuration
        pricing_config = PricingConfig.get_config()
        pricing_config.pricing_model = request.POST.get('pricing_model', 'single')
        pricing_config.save()
        
        # Create default price lists if multi-tier selected
        if pricing_config.pricing_model == 'multi':
            # Create retail price list
            PriceList.objects.get_or_create(
                code='RETAIL',
                defaults={
                    'name': request.POST.get('retail_name', 'Retail Price'),
                    'priority': 10,
                    'discount_method': 'fixed',
                    'applicable_to_retail': True,
                    'is_default': True
                }
            )
            
            # Create wholesale price list
            PriceList.objects.get_or_create(
                code='WHOLESALE',
                defaults={
                    'name': request.POST.get('wholesale_name', 'Wholesale Price'),
                    'priority': 20,
                    'discount_method': 'percentage',
                    'default_discount_percentage': 15,
                    'applicable_to_wholesale': True
                }
            )
            
            # Create distributor price list
            PriceList.objects.get_or_create(
                code='DISTRIBUTOR',
                defaults={
                    'name': request.POST.get('distributor_name', 'Distributor Price'),
                    'priority': 30,
                    'discount_method': 'percentage',
                    'default_discount_percentage': 25,
                    'applicable_to_distributor': True
                }
            )
        
        # Mark setup as completed
        settings.setup_completed = True
        settings.save()
        
        messages.success(request, "🎉 ERP setup completed successfully! You can now configure individual modules.")
        return redirect('admin:index')
    
    context = {
        'settings': settings,
        'modules': ModuleStatus.objects.all(),
    }
    return render(request, 'config_settings/setup_wizard.html', context)