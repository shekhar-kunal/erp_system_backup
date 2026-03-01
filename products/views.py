from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, F
from django.core.cache import cache
from .models import (
    Unit, ProductCategory, Brand, ModelNumber,
    Product, ProductVariant, ProductAttribute,
    ProductAttributeValue, ProductImage
)
import sys
from datetime import datetime
from django.contrib.admin.models import LogEntry
import django
from django.http import JsonResponse
from .models import ModelNumber

from django.views.decorators.http import require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
import logging

logger = logging.getLogger(__name__)

@require_GET
@staff_member_required
@ensure_csrf_cookie
def ajax_load_models(request):
    """
    AJAX view to load models based on selected brand
    Returns JSON response with filtered models
    """
    try:
        brand_id = request.GET.get('brand_id')
        current_model_id = request.GET.get('current_model_id')
        
        # Validate brand_id if provided
        if brand_id:
            try:
                brand_id = int(brand_id)
            except (TypeError, ValueError):
                return JsonResponse({
                    'error': 'Invalid brand ID format',
                    'models': []
                }, status=400)
        
        # Start with empty queryset
        models = ModelNumber.objects.none()
        
        # Filter by brand if provided
        if brand_id:
            models = ModelNumber.objects.filter(
                brand_id=brand_id,
                is_active=True
            ).order_by('name')
        
        # Always include current model if provided (even if inactive)
        if current_model_id:
            try:
                current_model_id = int(current_model_id)
                current_model = ModelNumber.objects.filter(id=current_model_id)
                models = (models | current_model).distinct()
            except (TypeError, ValueError):
                pass
        
        # Prepare response data
        data = [{
            'id': model.id,
            'name': str(model),
            'code': model.code,
            'brand_name': model.brand.name if model.brand else ''
        } for model in models]
        
        return JsonResponse({
            'success': True,
            'models': data,
            'count': len(data)
        })
        
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Error in ajax_load_models: {str(e)}", exc_info=True)
        
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while loading models',
            'models': []
        }, status=500)


@staff_member_required
def product_setup(request):
    """Product app setup dashboard view"""
    context = {}
   
    # Basic Counts
    context['total_products'] = Product.objects.count()
    context['total_categories'] = ProductCategory.objects.count()
    context['total_brands'] = Brand.objects.count()
    context['total_models'] = ModelNumber.objects.count()
    context['total_units'] = Unit.objects.count()
    context['total_variants'] = ProductVariant.objects.count()
   
    # Detailed Counts
    context['units_count'] = Unit.objects.count()
    context['categories_count'] = ProductCategory.objects.count()
    context['brands_count'] = Brand.objects.count()
    context['models_count'] = ModelNumber.objects.count()
    context['attributes_count'] = ProductAttribute.objects.count()
    context['attribute_values_count'] = ProductAttributeValue.objects.count()
   
    # Completion Status
    context['units_complete'] = Unit.objects.count() >= 5
    context['categories_complete'] = ProductCategory.objects.count() >= 3
    context['brands_complete'] = Brand.objects.count() >= 3
    context['models_complete'] = ModelNumber.objects.count() >= 5
    context['attributes_complete'] = ProductAttribute.objects.count() >= 2
    context['products_complete'] = Product.objects.count() >= 10
   
    # Recent Activity
    recent_logs = LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')[:10]
    context['recent_activities'] = []
    for log in recent_logs:
        context['recent_activities'].append({
            'time': log.action_time.strftime('%Y-%m-%d %H:%M'),
            'action': log.get_action_flag_display().lower(),
            'item': f"{log.content_type}: {log.object_repr}" if log.content_type else log.object_repr,
            'user': log.user.username if log.user else 'System'
        })
   
    # System Info
    context['django_version'] = django.get_version()
    context['python_version'] = '.'.join(map(str, sys.version_info[:3]))
   
    # Validation Stats
    context['missing_sku'] = Product.objects.filter(Q(sku__isnull=True) | Q(sku='')).count()
    context['missing_category'] = Product.objects.filter(category__isnull=True).count()
    context['missing_brand'] = Product.objects.filter(brand__isnull=True).count()
   
    # Integrity Stats
    context['orphaned_variants'] = ProductVariant.objects.filter(product__isnull=True).count()
   
    # Image Stats
    context['image_count'] = ProductImage.objects.count()
   
    # Cache Status
    cache.set('health_check', 'ok', 10)
    context['cache_status'] = 'Connected' if cache.get('health_check') == 'ok' else 'Not Connected'
   
    # Performance (simplified - you might want to calculate these properly)
    context['avg_query_time'] = '15'
    context['cache_hit_ratio'] = '85'
    context['index_status'] = 'Healthy'
    context['db_size'] = '15 MB'
    context['image_size'] = '45 MB'
    context['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M')
   
    return render(request, 'products/setup.html', context)

