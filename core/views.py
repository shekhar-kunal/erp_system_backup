# core/views.py
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from .models import Region, City, Country
import logging

logger = logging.getLogger(__name__)


def ajax_load_regions(request):
    """AJAX endpoint to load regions for a given country"""
    try:
        country_id = request.GET.get('country')
        if not country_id:
            return JsonResponse([], safe=False)
        
        # Validate country_id is a valid integer
        try:
            country_id = int(country_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid country ID'}, status=400)
        
        regions = Region.objects.filter(
            country_id=country_id,
            is_active=True
        ).order_by('name').values('id', 'name')
        
        return JsonResponse(list(regions), safe=False)
    
    except Exception as e:
        logger.error(f"Error loading regions: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)


def ajax_load_cities(request):
    """AJAX endpoint to load cities for a given country"""
    try:
        country_id = request.GET.get('country')
        if not country_id:
            return JsonResponse([], safe=False)
        
        # Validate country_id is a valid integer
        try:
            country_id = int(country_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid country ID'}, status=400)
        
        cities = City.objects.filter(
            country_id=country_id,
            is_active=True
        ).order_by('name').values('id', 'name')
        
        return JsonResponse(list(cities), safe=False)
    
    except Exception as e:
        logger.error(f"Error loading cities: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)


def ajax_load_cities_by_region(request):
    """AJAX endpoint to load cities for a given region"""
    try:
        region_id = request.GET.get('region')
        if not region_id:
            return JsonResponse([], safe=False)
        
        # Validate region_id is a valid integer
        try:
            region_id = int(region_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid region ID'}, status=400)
        
        cities = City.objects.filter(
            region_id=region_id,
            is_active=True
        ).order_by('name').values('id', 'name')
        
        return JsonResponse(list(cities), safe=False)
    
    except Exception as e:
        logger.error(f"Error loading cities by region: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)