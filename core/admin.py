from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count
from .models import Country, Region, City


class RegionInline(admin.TabularInline):
    model = Region
    extra = 1
    fields = ['name', 'code', 'is_active', 'position']
    ordering = ['position']


class CityInline(admin.TabularInline):
    model = City
    extra = 1
    fields = ['name', 'region', 'is_capital', 'is_active', 'position']
    ordering = ['position', 'name']
    autocomplete_fields = ['region']


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'iso_code', 'phone_code', 
        'currency', 'currency_symbol', 'region_count_display', 
        'city_count_display', 'usage_badge_display', 'is_active'
    ]
    list_filter = ['is_active']
    search_fields = ['name', 'code', 'iso_code']
    ordering = ['position', 'name']
    list_editable = ['is_active']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'iso_code', 'phone_code', 'is_active', 'position')
        }),
        ('Currency', {
            'fields': ('currency', 'currency_symbol')
        }),
        ('Additional Info', {
            'fields': ('default_timezone',),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [RegionInline, CityInline]

    def region_count_display(self, obj):
        count = obj.regions.count()
        return mark_safe(f'<b>{count}</b>')
    region_count_display.short_description = 'Regions'

    def city_count_display(self, obj):
        count = obj.cities.count()
        return mark_safe(f'<b>{count}</b>')
    city_count_display.short_description = 'Cities'

    def usage_badge_display(self, obj):
        # Count usage
        vendor_count = obj.vendors.count() if hasattr(obj, 'vendors') else 0
        billing_count = obj.billing_customers.count() if hasattr(obj, 'billing_customers') else 0
        shipping_count = obj.shipping_customers.count() if hasattr(obj, 'shipping_customers') else 0
        total_usage = vendor_count + billing_count + shipping_count
        
        if total_usage > 0:
            return mark_safe(
                f'<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 10px;">{total_usage} used</span>'
            )
        return mark_safe(
            '<span style="background-color: #6c757d; color: white; padding: 3px 8px; border-radius: 10px;">Not used</span>'
        )
    usage_badge_display.short_description = 'Usage'

    actions = ['deactivate_selected_with_warning']

    def deactivate_selected_with_warning(self, request, queryset):
        deactivated = 0
        skipped = 0
        skipped_names = []
        
        for country in queryset:
            vendor_count = country.vendors.count() if hasattr(country, 'vendors') else 0
            customer_count = 0
            if hasattr(country, 'billing_customers'):
                customer_count += country.billing_customers.count()
            if hasattr(country, 'shipping_customers'):
                customer_count += country.shipping_customers.count()
            
            total_usage = vendor_count + customer_count
            
            if total_usage > 0:
                skipped += 1
                skipped_names.append(f"{country.name} ({total_usage} uses)")
            else:
                country.is_active = False
                country.save()
                deactivated += 1
        
        if deactivated > 0:
            self.message_user(request, f"✅ {deactivated} countries deactivated.")
        if skipped > 0:
            self.message_user(
                request, 
                f"⚠️ Skipped {skipped} countries in use: {', '.join(skipped_names)}", 
                level='WARNING'
            )
    
    deactivate_selected_with_warning.short_description = "Deactivate selected (skip if in use)"


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'country', 'city_count_display', 'status_badge_display', 'is_active', 'position']
    list_filter = ['country', 'is_active']
    search_fields = ['name', 'code', 'country__name']
    list_editable = ['is_active', 'position']
    autocomplete_fields = ['country']
    
    inlines = [CityInline]

    def city_count_display(self, obj):
        count = obj.cities.count()
        return mark_safe(f'<b>{count}</b>')
    city_count_display.short_description = 'Cities'

    def status_badge_display(self, obj):
        city_count = obj.cities.count()
        if city_count > 0:
            return mark_safe(
                f'<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 10px;">{city_count} cities</span>'
            )
        return mark_safe(
            '<span style="background-color: #6c757d; color: white; padding: 3px 8px; border-radius: 10px;">No cities</span>'
        )
    status_badge_display.short_description = 'Status'


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'region', 'country', 'is_capital', 
        'usage_badge_display', 'is_active', 'position'
    ]
    list_filter = ['country', 'region', 'is_active', 'is_capital']
    search_fields = ['name', 'region__name', 'country__name']
    list_editable = ['is_active', 'position']
    autocomplete_fields = ['country', 'region']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'country', 'region', 'state', 'is_active', 'position')
        }),
        ('Geographic Data', {
            'fields': ('latitude', 'longitude', 'timezone', 'postal_code'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('is_capital', 'population'),
            'classes': ('collapse',)
        }),
    )

    def usage_badge_display(self, obj):
        # Count usage
        vendor_count = obj.vendors.count() if hasattr(obj, 'vendors') else 0
        billing_count = obj.billing_customers.count() if hasattr(obj, 'billing_customers') else 0
        shipping_count = obj.shipping_customers.count() if hasattr(obj, 'shipping_customers') else 0
        total_usage = vendor_count + billing_count + shipping_count
        
        if total_usage > 0:
            return mark_safe(
                f'<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 10px;">⬤ In Use ({total_usage})</span>'
            )
        return mark_safe(
            '<span style="background-color: #6c757d; color: white; padding: 3px 8px; border-radius: 10px;">○ Not Used</span>'
        )
    usage_badge_display.short_description = 'Status'

    actions = ['activate_selected', 'deactivate_selected_with_check']

    def activate_selected(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"✅ {count} cities activated.")
    activate_selected.short_description = "Activate selected cities"

    def deactivate_selected_with_check(self, request, queryset):
        deactivated = 0
        skipped = 0
        skipped_names = []
        
        for city in queryset:
            vendor_count = city.vendors.count() if hasattr(city, 'vendors') else 0
            customer_count = 0
            if hasattr(city, 'billing_customers'):
                customer_count += city.billing_customers.count()
            if hasattr(city, 'shipping_customers'):
                customer_count += city.shipping_customers.count()
            
            total_usage = vendor_count + customer_count
            
            if total_usage > 0:
                skipped += 1
                skipped_names.append(f"{city.name} ({total_usage} uses)")
            else:
                city.is_active = False
                city.save()
                deactivated += 1
        
        if deactivated > 0:
            self.message_user(request, f"✅ {deactivated} cities deactivated.")
        if skipped > 0:
            self.message_user(
                request, 
                f"⚠️ Skipped {skipped} cities in use: {', '.join(skipped_names)}", 
                level='WARNING'
            )
    
    deactivate_selected_with_check.short_description = "Deactivate selected (skip if in use)"