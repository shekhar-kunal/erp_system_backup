from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html, mark_safe
from django.urls import path
from django.shortcuts import redirect, render
from django.db.models import Sum, F
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime
import csv
from exports.mixins import ConfigurableExportMixin
from exports.column_config import ColumnConfigMixin
from rbac.admin_mixins import ERPAdminMixin

from .models import (
    Warehouse, WarehouseSection, Stock, StockBatch, 
    StockMovement, StockCount, StockCountLine, InventorySettings
)
from .forms import (
    ManualMovementForm, StockFilterForm, StockBatchForm,
    StockCountForm, StockCountLineForm
)
from .dashboard import InventoryDashboard
from .mixins import DashboardMixin


# ===================== WAREHOUSE ADMIN =====================

@admin.register(Warehouse)
class WarehouseAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, DashboardMixin, admin.ModelAdmin):
    export_fields = ['name', 'code', 'warehouse_type', 'temperature_zone', 'address', 'phone', 'email', 'is_active', 'created_at']
    export_methods = {
        'warehouse_type': lambda obj: obj.get_warehouse_type_display(),
        'is_active': lambda obj: 'Yes' if obj.is_active else 'No',
    }
    ALL_LIST_COLUMNS = [
        ('name', 'Name'),
        ('code', 'Code'),
        ('warehouse_type', 'Type'),
        ('is_active', 'Active'),
        ('capacity_display', 'Capacity'),
        ('utilization_indicator', 'Utilization'),
        ('stock_value_display', 'Stock Value'),
        ('item_count', 'Items'),
        ('last_updated', 'Last Movement'),
    ]
    DEFAULT_COLUMNS = ['name', 'code', 'warehouse_type', 'is_active', 'capacity_display', 'stock_value_display', 'item_count']
    REQUIRED_COLUMNS = ['name']

    list_display = [
        'name', 'code', 'warehouse_type', 'is_active',
        'capacity_display', 'utilization_indicator', 'stock_value_display',
        'item_count', 'last_updated'
    ]
    list_filter = ['warehouse_type', 'is_active', 'temperature_zone']
    search_fields = ['name', 'code', 'address']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'warehouse_type', 'temperature_zone')
        }),
        ('Contact Information', {
            'fields': ('address', 'phone', 'email', 'manager')
        }),
        ('Capacity', {
            'fields': ('capacity', 'capacity_unit', 'utilization_threshold')
        }),
        ('Status', {
            'fields': ('is_active', 'notes', 'operating_hours', 'meta_data')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'capacity_unit', 'manager'
        ).prefetch_related('stock_entries')
    
    def capacity_display(self, obj):
        """Display capacity with unit"""
        if obj.capacity and obj.capacity_unit:
            formatted_capacity = "{:,.2f}".format(obj.capacity)
            return format_html('{} {}', formatted_capacity, obj.capacity_unit.code)
        return mark_safe('<span style="color: #6c757d;">—</span>')
    capacity_display.short_description = 'Capacity'
    
    def utilization_indicator(self, obj):
        """Display warehouse utilization as a colored progress bar"""
        # Calculate utilization (you might have this as a property)
        if obj.capacity and obj.capacity > 0:
            # This assumes you have a way to get current occupancy
            # You might need to customize this based on your model
            utilization = 0  # Replace with actual calculation
        else:
            utilization = 0
        
        if utilization >= 90:
            color = '#dc3545'
            status = 'Critical'
        elif utilization >= 75:
            color = '#ffc107'
            status = 'Warning'
        elif utilization >= 50:
            color = '#17a2b8'
            status = 'Good'
        else:
            color = '#28a745'
            status = 'Excellent'
        
        # Format the percentage as a string first
        utilization_str = "{:.1f}".format(utilization)
        
        return format_html(
            '<div style="width:100px;">'
            '<div style="background-color:#e9ecef; border-radius:4px; height:20px; width:100%;">'
            '<div style="background-color:{}; width:{}%; height:20px; border-radius:4px; text-align:center; line-height:20px; color:white; font-size:10px;">'
            '{}%'
            '</div></div>'
            '<small style="color:{};">{}</small></div>',
            color, utilization, utilization_str, color, status
        )
    utilization_indicator.short_description = 'Utilization'
    
    def stock_value_display(self, obj):
        """Calculate total value of stock in this warehouse"""
        try:
            result = obj.stock_entries.aggregate(
                total=Sum(F('quantity') * F('product__cost'))
            )['total'] or 0
            
            # Format the number as a string first
            formatted_value = "{:,.2f}".format(result)
            return format_html('${}', formatted_value)
            
        except Exception:
            return format_html('<span style="color: #6c757d;">{}</span>', 'N/A')
    stock_value_display.short_description = 'Stock Value'
    
    def item_count(self, obj):
        """Count number of unique products in warehouse"""
        count = obj.stock_entries.filter(quantity__gt=0).count()
        return format_html('{}', count)
    item_count.short_description = 'Items'
    
    def last_updated(self, obj):
        """Show last stock movement date"""
        latest = obj.stock_entries.order_by('-last_movement').first()
        if latest and latest.last_movement:
            date_str = latest.last_movement.strftime('%Y-%m-%d')
            return format_html('{}', date_str)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    last_updated.short_description = 'Last Movement'
    
    actions = ['mark_active', 'mark_inactive']
    
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} warehouses marked as active.')
    mark_active.short_description = "Mark selected as active"
    
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} warehouses marked as inactive.')
    mark_inactive.short_description = "Mark selected as inactive"


# ===================== WAREHOUSE SECTION ADMIN =====================

@admin.register(WarehouseSection)
class WarehouseSectionAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = [
        'full_location', 'warehouse', 'barcode_display',
        'max_capacity_display', 'current_occupancy_display', 'utilization_display',
        'is_active'
    ]
    list_filter = ['warehouse', 'is_active']
    search_fields = ['zone', 'aisle', 'rack', 'bin', 'barcode']
    
    fieldsets = (
        ('Location', {
            'fields': ('warehouse', 'zone', 'aisle', 'rack', 'bin', 'barcode')
        }),
        ('Capacity', {
            'fields': ('max_capacity', 'current_occupancy')
        }),
        ('Status', {
            'fields': ('description', 'is_active')
        }),
    )
    
    def full_location(self, obj):
        return format_html('<b>{}</b>', obj.full_location)
    full_location.short_description = 'Location'
    
    def barcode_display(self, obj):
        if obj.barcode:
            return format_html('<code>{}</code>', obj.barcode)
        return mark_safe('<span style="color: #6c757d;">—</span>')
    barcode_display.short_description = 'Barcode'
    
    def max_capacity_display(self, obj):
        if obj.max_capacity:
            formatted = "{:,.2f}".format(obj.max_capacity)
            return format_html('{}', formatted)
        return mark_safe('<span style="color: #6c757d;">—</span>')
    max_capacity_display.short_description = 'Max Capacity'
    
    def current_occupancy_display(self, obj):
        formatted = "{:,.2f}".format(obj.current_occupancy)
        return format_html('{}', formatted)
    current_occupancy_display.short_description = 'Current Occupancy'
    
    def utilization_display(self, obj):
        """Display utilization percentage"""
        util = obj.utilization_percentage
        formatted_util = "{:.1f}".format(util)
        
        if util >= 90:
            return format_html('<span style="color: #dc3545;">{}%</span>', formatted_util)
        elif util >= 75:
            return format_html('<span style="color: #ffc107;">{}%</span>', formatted_util)
        else:
            return format_html('<span style="color: #28a745;">{}%</span>', formatted_util)
    utilization_display.short_description = 'Utilization'
    
    actions = ['generate_barcodes']
    
    def generate_barcodes(self, request, queryset):
        updated = 0
        for section in queryset:
            if not section.barcode:
                section.barcode = f"{section.warehouse.code}-{section.zone}{section.aisle}{section.rack}{section.bin}"
                section.save()
                updated += 1
        self.message_user(request, f'Generated barcodes for {updated} sections.')
    generate_barcodes.short_description = "Generate barcodes for selected"


# ===================== STOCK ADMIN =====================

@admin.register(Stock)
class StockAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, DashboardMixin, admin.ModelAdmin):
    ALL_LIST_COLUMNS = [
        ('product_link', 'Product'),
        ('warehouse_link', 'Warehouse'),
        ('section_link', 'Section'),
        ('quantity_display', 'Quantity'),
        ('unit_info', 'Unit'),
        ('available_display', 'Available'),
        ('reorder_level', 'Reorder Level'),
        ('status_indicator', 'Status'),
        ('batch_count', 'Batches'),
        ('value_display', 'Value'),
        ('last_movement_display', 'Last Movement'),
    ]
    DEFAULT_COLUMNS = ['product_link', 'warehouse_link', 'quantity_display', 'available_display', 'reorder_level', 'status_indicator', 'value_display']
    REQUIRED_COLUMNS = ['product_link']

    list_display = [
        'product_link', 'warehouse_link', 'section_link',
        'quantity_display', 'unit_info', 'available_display',
        'reorder_level', 'status_indicator', 'batch_count',
        'value_display', 'last_movement_display'
    ]
    list_filter = [
        'warehouse', 'section__warehouse', 'product__category',
        'is_frozen', 'last_counted'
    ]
    search_fields = ['product__name', 'product__sku', 'warehouse__name']
    readonly_fields = ['quantity', 'last_movement', 'created_at', 'updated_at']
    list_editable = ['reorder_level']
    export_fields = [
        'product__name', 'product__sku', 'warehouse__name', 'section__full_location',
        'quantity', 'unit__code', 'reorder_level', 'max_level', 'reserved_quantity',
        'is_frozen', 'last_movement',
    ]
    export_methods = {
        'product__name': lambda obj: obj.product.name if obj.product else '',
        'product__sku': lambda obj: obj.product.sku if obj.product else '',
        'warehouse__name': lambda obj: obj.warehouse.name if obj.warehouse else '',
        'section__full_location': lambda obj: obj.section.full_location if obj.section else '',
        'unit__code': lambda obj: obj.unit.code if obj.unit else '',
        'is_frozen': lambda obj: 'Yes' if obj.is_frozen else 'No',
    }
    export_sheet_name = 'Stock'

    actions = [
        'freeze_stock', 'unfreeze_stock', 'create_count_sheet',
        'bulk_update_reorder_level'
    ]
    
    fieldsets = (
        ('Product Location', {
            'fields': ('product', 'warehouse', 'section')
        }),
        ('Stock Levels', {
            'fields': ('quantity', 'unit', 'unit_quantity', 'reorder_level', 'max_level', 'safety_stock')
        }),
        ('Reservations', {
            'fields': ('reserved_quantity',),
            'classes': ('collapse',)
        }),
        ('Status Information', {
            'fields': ('is_frozen', 'last_counted', 'last_movement', 'notes')
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    class Media:
        css = {
            'all': ('css/admin/inventory.css',)
        }
        js = ('js/admin/stock.js',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'warehouse', 'section', 'unit'
        ).prefetch_related('batches')

    def product_link(self, obj):
        """Link to product detail page"""
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = 'Product'
    product_link.admin_order_field = 'product__name'

    def warehouse_link(self, obj):
        """Link to warehouse detail page"""
        url = reverse('admin:inventory_warehouse_change', args=[obj.warehouse.id])
        return format_html('<a href="{}">{}</a>', url, obj.warehouse.name)
    warehouse_link.short_description = 'Warehouse'
    warehouse_link.admin_order_field = 'warehouse__name'

    def section_link(self, obj):
        """Link to section if exists"""
        if obj.section:
            url = reverse('admin:inventory_warehousesection_change', args=[obj.section.id])
            return format_html('<a href="{}">{}</a>', url, obj.section.full_location)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    section_link.short_description = 'Section'

    def quantity_display(self, obj):
        """Display quantity with unit"""
        # Format the quantity as a string first
        formatted_qty = "{:.2f}".format(obj.quantity)
        
        if obj.unit:
            unit_code = getattr(obj.unit, 'code', getattr(obj.unit, 'short_name', 'unit'))
            return format_html('<b>{}</b> {}', formatted_qty, unit_code)
        return format_html('<b>{}</b>', formatted_qty)
    quantity_display.short_description = 'Quantity'
    quantity_display.admin_order_field = 'quantity'

    def unit_info(self, obj):
        """Display unit information"""
        if obj.unit:
            unit_name = getattr(obj.unit, 'name', '')
            unit_code = getattr(obj.unit, 'code', '')
            return format_html('{} ({})', unit_name, unit_code)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    unit_info.short_description = 'Unit'

    def available_display(self, obj):
        """Display available quantity"""
        available = obj.available_quantity
        formatted_available = "{:.2f}".format(available)
        
        if available <= 0:
            return format_html('<span style="color: #dc3545;">{}</span>', formatted_available)
        elif available < obj.reorder_level:
            return format_html('<span style="color: #fd7e14;">{}</span>', formatted_available)
        else:
            return format_html('<span style="color: #28a745;">{}</span>', formatted_available)
    available_display.short_description = 'Available'
    available_display.admin_order_field = 'quantity'

    def status_indicator(self, obj):
        """Display status with color coding"""
        if obj.is_frozen:
            return mark_safe('<span style="color: #6c757d;">❄️ Frozen</span>')
        if obj.quantity <= 0:
            return mark_safe('<span style="color: #dc3545;">🔴 Out of Stock</span>')
        if obj.needs_reorder:
            return mark_safe('<span style="color: #fd7e14;">🟡 Reorder Needed</span>')
        if obj.is_low_stock:
            return mark_safe('<span style="color: #ffc107;">🟡 Low Stock</span>')
        if obj.is_overstocked:
            return mark_safe('<span style="color: #6f42c1;">🟣 Overstocked</span>')
        return mark_safe('<span style="color: #28a745;">🟢 In Stock</span>')
    status_indicator.short_description = 'Status'

    def batch_count(self, obj):
        """Count number of batches for this stock"""
        count = obj.batches.count()
        if count:
            url = reverse('admin:inventory_stockbatch_changelist') + f'?stock__id__exact={obj.id}'
            return format_html('<a href="{}">{}</a>', url, count)
        return format_html('<span style="color: #6c757d;">{}</span>', '0')
    batch_count.short_description = 'Batches'

    def value_display(self, obj):
        """Display total value of this stock"""
        value = obj.quantity * (obj.product.cost or 0)
        formatted_value = "{:,.2f}".format(value)
        return format_html('${}', formatted_value)
    value_display.short_description = 'Value'

    def last_movement_display(self, obj):
        """Display last movement date"""
        if obj.last_movement:
            date_str = obj.last_movement.strftime('%Y-%m-%d %H:%M')
            return format_html('{}', date_str)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    last_movement_display.short_description = 'Last Movement'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('manual-movement/<int:stock_id>/',
                 self.admin_site.admin_view(self.manual_movement),
                 name='stock-manual-movement'),
        ]
        return custom_urls + urls

    def manual_movement(self, request, stock_id):
        """Handle manual stock movement"""
        stock = Stock.objects.get(id=stock_id)
        
        if request.method == 'POST':
            form = ManualMovementForm(request.POST)
            if form.is_valid():
                qty = form.cleaned_data['quantity']
                try:
                    if qty > 0:
                        stock.add_stock(
                            qty=abs(qty),
                            source=form.cleaned_data['source'],
                            reference=form.cleaned_data['reference'],
                            notes=form.cleaned_data['notes'],
                            user=request.user
                        )
                        messages.success(request, f"Added {qty} units to stock")
                    else:
                        stock.remove_stock(
                            qty=abs(qty),
                            source=form.cleaned_data['source'],
                            reference=form.cleaned_data['reference'],
                            notes=form.cleaned_data['notes'],
                            user=request.user
                        )
                        messages.success(request, f"Removed {abs(qty)} units from stock")
                    
                    return redirect(f'../../{stock.id}/change/')
                except Exception as e:
                    messages.error(request, f"Error: {str(e)}")
        else:
            form = ManualMovementForm()
        
        context = {
            **self.admin_site.each_context(request),
            'title': f'Manual Stock Movement - {stock.product.name} @ {stock.warehouse.name}',
            'stock': stock,
            'form': form,
        }
        return render(request, 'admin/inventory/manual_movement.html', context)

    # Actions
    def freeze_stock(self, request, queryset):
        updated = queryset.update(is_frozen=True)
        self.message_user(request, f"{updated} stock items frozen.")
    freeze_stock.short_description = "Freeze selected stock"

    def unfreeze_stock(self, request, queryset):
        updated = queryset.update(is_frozen=False)
        self.message_user(request, f"{updated} stock items unfrozen.")
    unfreeze_stock.short_description = "Unfreeze selected stock"

    def create_count_sheet(self, request, queryset):
        """Create a stock count sheet from selected items"""
        if 'apply' in request.POST:
            count_name = request.POST.get('count_name')
            warehouse_id = request.POST.get('warehouse')
            
            if not count_name or not warehouse_id:
                self.message_user(request, "Please provide count name and warehouse.", messages.ERROR)
                return redirect(request.get_full_path())
            
            stock_count = StockCount.objects.create(
                name=count_name,
                warehouse_id=warehouse_id,
                created_by=request.user,
                status='draft'
            )
            
            for stock in queryset:
                StockCountLine.objects.create(
                    stock_count=stock_count,
                    product=stock.product,
                    expected_quantity=stock.quantity
                )
            
            self.message_user(
                request, 
                f"Count sheet '{count_name}' created with {queryset.count()} items.",
                messages.SUCCESS
            )
            return redirect(f'/admin/inventory/stockcount/{stock_count.id}/change/')
        
        from .models import Warehouse
        context = {
            'title': 'Create Stock Count Sheet',
            'queryset': queryset,
            'warehouses': Warehouse.objects.filter(is_active=True),
        }
        return render(request, 'admin/inventory/create_count_sheet.html', context)
    create_count_sheet.short_description = "Create count sheet"


    def bulk_update_reorder_level(self, request, queryset):
        """Bulk update reorder level for selected stock"""
        if 'apply' in request.POST:
            new_level = request.POST.get('new_reorder_level')
            if new_level:
                try:
                    new_level = float(new_level)
                    updated = queryset.update(reorder_level=new_level)
                    self.message_user(request, f"Updated reorder level to {new_level} for {updated} items.")
                except ValueError:
                    self.message_user(request, "Invalid reorder level value.", messages.ERROR)
            return redirect(request.get_full_path())
        
        context = {
            'title': 'Bulk Update Reorder Level',
            'queryset': queryset,
        }
        return render(request, 'admin/inventory/bulk_update_reorder.html', context)
    bulk_update_reorder_level.short_description = "Bulk update reorder level"


# ===================== STOCK BATCH ADMIN =====================

@admin.register(StockBatch)
class StockBatchAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = [
        'batch_number', 'stock_link', 'quantity_display', 'unit_info',
        'expiry_date_display', 'quality_status', 'is_active', 'received_date_display'
    ]
    list_filter = ['quality_status', 'is_active', 'received_date', 'expiry_date']
    search_fields = ['batch_number', 'supplier_batch', 'supplier', 'stock__product__name']
    readonly_fields = ['received_date', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Batch Information', {
            'fields': ('stock', 'batch_number', 'supplier_batch', 'supplier')
        }),
        ('Quantity & Unit', {
            'fields': ('quantity', 'unit', 'unit_quantity')
        }),
        ('Dates', {
            'fields': (('received_date', 'expiry_date', 'manufacturing_date'),)
        }),
        ('Quality', {
            'fields': ('quality_status', 'notes', 'is_active'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def stock_link(self, obj):
        """Link to stock record"""
        if obj.stock:
            url = reverse('admin:inventory_stock_change', args=[obj.stock.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.stock))
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    stock_link.short_description = 'Stock'
    
    def quantity_display(self, obj):
        """Display quantity with formatting"""
        formatted_qty = "{:.2f}".format(obj.quantity)
        
        if obj.unit:
            unit_code = getattr(obj.unit, 'code', getattr(obj.unit, 'short_name', 'unit'))
            return format_html('<b>{}</b> {}', formatted_qty, unit_code)
        return format_html('<b>{}</b>', formatted_qty)
    quantity_display.short_description = 'Quantity'
    
    def unit_info(self, obj):
        """Display unit information"""
        if obj.unit:
            unit_name = getattr(obj.unit, 'name', '')
            unit_code = getattr(obj.unit, 'code', '')
            return format_html('{} ({})', unit_name, unit_code)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    unit_info.short_description = 'Unit'
    
    def expiry_date_display(self, obj):
        """Display expiry date with color coding"""
        if not obj.expiry_date:
            return mark_safe('<span style="color: #6c757d;">—</span>')
        
        date_str = obj.expiry_date.strftime('%Y-%m-%d')
        days_until = (obj.expiry_date - timezone.now().date()).days
        
        if days_until < 0:
            return format_html('<span style="color: #dc3545;">{} (Expired)</span>', date_str)
        elif days_until < 30:
            return format_html('<span style="color: #fd7e14;">{} (Expiring soon)</span>', date_str)
        else:
            return format_html('{}', date_str)
    expiry_date_display.short_description = 'Expiry Date'
    expiry_date_display.admin_order_field = 'expiry_date'
    
    def received_date_display(self, obj):
        """Display received date formatted"""
        if obj.received_date:
            date_str = obj.received_date.strftime('%Y-%m-%d')
            return format_html('{}', date_str)
        return format_html('<span style="color: #6c757d;">{}</span>', '—')
    received_date_display.short_description = 'Received Date'
    received_date_display.admin_order_field = 'received_date'
    
    actions = ['mark_as_quality_approved', 'mark_as_quality_rejected', 'mark_as_active', 'mark_as_inactive']
    
    def mark_as_quality_approved(self, request, queryset):
        updated = queryset.update(quality_status='accepted')
        self.message_user(request, f'{updated} batches marked as quality approved.')
    mark_as_quality_approved.short_description = "Mark selected as quality approved"
    
    def mark_as_quality_rejected(self, request, queryset):
        updated = queryset.update(quality_status='rejected')
        self.message_user(request, f'{updated} batches marked as quality rejected.')
    mark_as_quality_rejected.short_description = "Mark selected as quality rejected"
    
    def mark_as_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} batches marked as active.')
    mark_as_active.short_description = "Mark selected as active"
    
    def mark_as_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} batches marked as inactive.')
    mark_as_inactive.short_description = "Mark selected as inactive"


# ===================== STOCK MOVEMENT ADMIN =====================

@admin.register(StockMovement)
class StockMovementAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = [
        'id', 'product_link', 'warehouse', 'section',
        'movement_type_display', 'quantity_display', 'reference',
        'created_at', 'created_by'
    ]
    list_filter = ['movement_type', 'warehouse', 'created_at']
    search_fields = ['product__name', 'product__sku', 'reference', 'notes']
    readonly_fields = ['previous_balance', 'new_balance', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'  # Now using the correct field name
    
    fieldsets = (
        ('Movement Details', {
            'fields': ('product', 'warehouse', 'section', 'movement_type', 'quantity', 'unit_quantity')
        }),
        ('Reference', {
            'fields': ('reference', 'source', 'notes')
        }),
        ('Balances', {
            'fields': (('previous_balance', 'new_balance'),),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def product_link(self, obj):
        """Link to product detail"""
        from django.urls import reverse
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = 'Product'
    
    def movement_type_display(self, obj):
        """Display movement type with color"""
        if obj.movement_type == 'IN':
            return mark_safe('<span style="color: #28a745;">⬆️ IN</span>')
        elif obj.movement_type == 'OUT':
            return mark_safe('<span style="color: #dc3545;">⬇️ OUT</span>')
        elif obj.movement_type == 'TRANSFER':
            return mark_safe('<span style="color: #17a2b8;">🔄 TRANSFER</span>')
        return format_html('{}', obj.get_movement_type_display())
    movement_type_display.short_description = 'Type'
    
    def quantity_display(self, obj):
        """Display quantity with sign"""
        formatted_qty = "{:.2f}".format(abs(obj.quantity))
        
        if obj.movement_type == 'IN':
            return format_html('<span style="color: #28a745;">+{}</span>', formatted_qty)
        elif obj.movement_type == 'OUT':
            return format_html('<span style="color: #dc3545;">-{}</span>', formatted_qty)
        return format_html('{}', formatted_qty)
    quantity_display.short_description = 'Quantity'


# ===================== STOCK COUNT ADMIN =====================

class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    form = StockCountLineForm
    extra = 1
    fields = ['product', 'expected_quantity', 'counted_quantity', 'variance', 'notes']
    readonly_fields = ['variance']
    
    def variance(self, obj):
        if obj.counted_quantity is not None:
            diff = obj.counted_quantity - obj.expected_quantity
            formatted_diff = "{:.2f}".format(diff)
            if diff > 0:
                return format_html('<span style="color: #28a745;">+{}</span>', formatted_diff)
            elif diff < 0:
                return format_html('<span style="color: #dc3545;">{}</span>', formatted_diff)
            else:
                return mark_safe('<span style="color: #6c757d;">0</span>')
        return mark_safe('<span style="color: #6c757d;">—</span>')
    variance.short_description = 'Variance'


@admin.register(StockCount)
class StockCountAdmin(ERPAdminMixin, admin.ModelAdmin):
    inlines = [StockCountLineInline]
    list_display = [
        'name', 'warehouse', 'status', 'count_date',
        'total_items', 'completed_items', 'progress_bar',
        'created_by'
    ]
    list_filter = ['status', 'warehouse', 'count_date']
    search_fields = ['name', 'warehouse__name']
    readonly_fields = ['created_at']  # Remove updated_at if it doesn't exist
    
    fieldsets = (
        ('Count Information', {
            'fields': ('name', 'warehouse', 'status', 'count_date', 'notes')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_items(self, obj):
        return obj.lines.count()
    total_items.short_description = 'Total Items'
    
    def completed_items(self, obj):
        completed = obj.lines.filter(counted_quantity__isnull=False).count()
        return completed
    completed_items.short_description = 'Completed'
    
    def progress_bar(self, obj):
        total = obj.lines.count()
        if total == 0:
            return mark_safe('<span style="color: #6c757d;">—</span>')
        
        completed = obj.lines.filter(counted_quantity__isnull=False).count()
        percentage = (completed / total) * 100
        formatted_percentage = "{:.1f}".format(percentage)
        
        return format_html(
            '<div style="width:100px; background:#e9ecef; border-radius:4px;">'
            '<div style="background-color:#28a745; width:{}%; height:20px; border-radius:4px; text-align:center; color:white; line-height:20px; font-size:10px;">'
            '{}%</div></div>',
            percentage, formatted_percentage
        )
    progress_bar.short_description = 'Progress'
    
    actions = ['complete_count', 'cancel_count']
    
    def complete_count(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} stock counts marked as completed.')
    complete_count.short_description = "Mark as completed"
    
    def cancel_count(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} stock counts cancelled.')
    cancel_count.short_description = "Cancel selected"


# ===================== INVENTORY SETTINGS ADMIN =====================

@admin.register(InventorySettings)
class InventorySettingsAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['id']  # Remove updated_at and updated_by if they don't exist
    list_display_links = ['id']
    
    fieldsets = (
        ('Feature Toggles', {
            'fields': (
                ('enable_batch_tracking', 'enable_serial_tracking'),
                ('enable_damaged_goods', 'enable_reservations'),
                ('enable_cycle_counting', 'enable_auto_reorder'),
                'allow_backorders',
            )
        }),
        ('Valuation', {
            'fields': ('default_valuation_method',)
        }),
        ('Reservations', {
            'fields': ('reservation_expiry_hours',),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': ('low_stock_threshold', 'overstock_threshold'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one instance
        if InventorySettings.objects.exists():
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        return False