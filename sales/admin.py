from django.contrib import admin, messages
from django.utils.html import format_html, mark_safe
from django.urls import path
from django.shortcuts import redirect, render
from django import forms
from django.forms import modelformset_factory
from django.db import transaction
from django.db.models import F, Sum, Count
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Customer, SalesOrder, SalesOrderLine, SalesInvoice, Payment, SalesSettings, Quotation
from inventory.models import Stock
from .forms import CustomerAdminForm
from exports.mixins import ConfigurableExportMixin
from rbac.admin_mixins import ERPAdminMixin


# ============= SETTINGS ADMIN =============

@admin.register(SalesSettings)
class SalesSettingsAdmin(ERPAdminMixin, admin.ModelAdmin):
    """Global sales settings - singleton"""
    
    fieldsets = (
        ('Core Features', {
            'fields': (
                'enable_quotations',
                'enable_sales_orders',
                'enable_invoicing',
            ),
            'description': 'Enable or disable core sales features'
        }),
        ('Advanced Features', {
            'fields': (
                'enable_order_approval',
                'enable_delivery_notes',
                'enable_sales_returns',
                'enable_backorders',
                'enable_credit_limit',
            ),
            'description': 'Advanced sales features'
        }),
        ('Pricing Features', {
            'fields': (
                'enable_discounts',
                'enable_tax_calculation',
                'enable_profit_tracking',
            ),
            'description': 'Pricing and discount features'
        }),
        ('Approval Settings', {
            'fields': (
                'require_approval_for_amount',
                'auto_confirm_approved_orders',
            ),
            'description': 'Configure approval workflow'
        }),
        ('Numbering Prefixes', {
            'fields': (
                'quotation_prefix',
                'order_prefix',
                'invoice_prefix',
                'delivery_note_prefix',
                'return_prefix',
            ),
            'description': 'Set prefixes for document numbers'
        }),
        ('Defaults', {
            'fields': (
                'default_tax_rate',
                'quotation_valid_days',
            ),
            'description': 'Default values'
        }),
    )
    
    def has_add_permission(self, request):
        return not SalesSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


# ============= INLINES =============

class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1
    fields = ['product', 'quantity', 'price', 'warehouse', 'section', 'delivered_quantity', 'subtotal_display', 'pricing_info']
    readonly_fields = ['delivered_quantity', 'subtotal_display', 'pricing_info']

    def subtotal_display(self, obj):
        if obj.id:
            return format_html('<b>{}</b>', obj.subtotal)
        return "-"
    subtotal_display.short_description = "Subtotal"
    
    def pricing_info(self, obj):
        if obj.id and obj.order and obj.order.customer:
            tier = obj.order.customer.get_pricing_tier_display()
            if obj.order.customer.custom_discount_percentage:
                return format_html(
                    '<span style="color: #28a745;">Custom Discount: {}%</span>',
                    obj.order.customer.custom_discount_percentage
                )
            return format_html(
                '<span style="color: #417690;">Tier: {}</span>',
                tier
            )
        return "-"
    pricing_info.short_description = "Pricing"


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ['payment_date']
    fields = ['amount', 'payment_method', 'reference', 'payment_date']


# ============= DASHBOARD MIXIN =============

class SalesDashboardMixin:
    """Mixin to add dashboard view to sales admin"""
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', 
                 self.admin_site.admin_view(self.dashboard_view), 
                 name='sales-dashboard'),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
        """Sales dashboard with key metrics"""
        from datetime import date, timedelta
        from django.db.models import Sum, Count, F
        
        today = date.today()
        month_start = date(today.year, today.month, 1)
        week_start = today - timedelta(days=today.weekday())
        
        # Get settings
        settings = SalesSettings.get_settings()
        
        # Get orders for different periods
        orders_today = SalesOrder.objects.filter(order_date=today)
        orders_week = SalesOrder.objects.filter(order_date__gte=week_start)
        orders_month = SalesOrder.objects.filter(order_date__gte=month_start)
        
        # Calculate totals by summing line items (since total_amount is a property)
        orders_today_value = 0
        for order in orders_today:
            orders_today_value += order.total_amount
        
        orders_week_value = 0
        for order in orders_week:
            orders_week_value += order.total_amount
        
        orders_month_value = 0
        for order in orders_month:
            orders_month_value += order.total_amount
        
        # Invoice stats
        invoices_unpaid = SalesInvoice.objects.filter(
            status__in=['unpaid', 'partial']
        ).count()
        
        invoices_overdue = SalesInvoice.objects.filter(
            status__in=['unpaid', 'partial'],
            due_date__lt=today
        ).count()
        
        # Calculate total receivable
        total_receivable = 0
        for invoice in SalesInvoice.objects.filter(status__in=['unpaid', 'partial']):
            total_receivable += invoice.balance_due
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Sales Dashboard',
            'settings': settings,
            
            # Customer stats
            'total_customers': Customer.objects.count(),
            'active_customers': Customer.objects.filter(is_active=True).count(),
            'vip_customers': Customer.objects.filter(is_vip=True).count(),
            
            # Today's stats
            'orders_today': orders_today.count(),
            'orders_today_value': orders_today_value,
            
            # This week's stats
            'orders_week': orders_week.count(),
            'orders_week_value': orders_week_value,
            
            # This month's stats
            'orders_month': orders_month.count(),
            'orders_month_value': orders_month_value,
            
            # Invoice stats
            'invoices_unpaid': invoices_unpaid,
            'invoices_overdue': invoices_overdue,
            'total_receivable': total_receivable,
            
            # Quotation stats (if enabled)
            'quotations_pending': Quotation.objects.filter(
                status='sent'
            ).count() if settings.enable_quotations else 0,
            
            # Recent orders
            'recent_orders': SalesOrder.objects.order_by('-order_date')[:10],
        }
        
        # 👇 FIXED: Correct template path
        return render(request, "admin/sales/dashboard.html", context)


# ============= DELIVERY FORM =============

class DeliveryForm(forms.Form):
    """Form for bulk delivery of multiple lines"""
    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order')
        super().__init__(*args, **kwargs)
        
        for line in self.order.lines.all():
            if line.remaining_quantity > 0:
                field_name = f'line_{line.id}'
                self.fields[field_name] = forms.DecimalField(
                    label=f"{line.product.name} (Max: {line.remaining_quantity})",
                    min_value=0,
                    max_value=line.remaining_quantity,
                    initial=0,
                    required=False,
                    help_text=f"Enter quantity to deliver"
                )


# ============= CUSTOMER ADMIN =============

@admin.register(Customer)
class CustomerAdmin(ERPAdminMixin, ConfigurableExportMixin, admin.ModelAdmin):
    form = CustomerAdminForm
    export_fields = [
        'full_name', 'email', 'phone', 'customer_type', 'payment_type',
        'pricing_tier', 'billing_country__name', 'billing_city__name',
        'is_vip', 'is_active', 'customer_code', 'created_at',
    ]
    export_methods = {
        'customer_type': lambda obj: obj.get_customer_type_display(),
        'payment_type': lambda obj: obj.get_payment_type_display(),
        'pricing_tier': lambda obj: obj.get_pricing_tier_display(),
        'billing_country__name': lambda obj: obj.billing_country.name if obj.billing_country else '',
        'billing_city__name': lambda obj: obj.billing_city.name if obj.billing_city else '',
        'is_vip': lambda obj: 'Yes' if obj.is_vip else 'No',
        'is_active': lambda obj: 'Yes' if obj.is_active else 'No',
    }
    list_display = (
        'full_name', 'email', 'phone', 'customer_type', 
        'payment_type', 'pricing_tier', 'pricing_tier_colored',
        'billing_country', 'is_vip'
    )
    list_filter = (
        'customer_type', 'payment_type', 'is_active', 'is_vip', 
        'billing_country', 'pricing_tier'
    )
    search_fields = ('first_name', 'last_name', 'email', 'customer_code', 'company_name')
    ordering = ('position', 'full_name')
    list_editable = ('pricing_tier',)
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('first_name', 'last_name', 'full_name', 'email', 'phone', 'date_of_birth')
        }),
        ('Pricing Configuration', {
            'fields': ('pricing_tier', 'custom_price_list', 'custom_discount_percentage'),
            'classes': ('wide',),
            'description': 'Configure how prices are calculated for this customer'
        }),
        ('Billing Address', {
            'fields': (
                'billing_address_line1', 'billing_address_line2',
                'billing_country', 'billing_region', 'billing_city', 'billing_postal_code',
                'same_as_billing'
            )
        }),
        ('Shipping Address', {
            'fields': (
                'shipping_address_line1', 'shipping_address_line2',
                'shipping_country', 'shipping_region', 'shipping_city', 'shipping_postal_code'
            )
        }),
        ('Business Info', {
            'fields': (
                'customer_type', 'payment_type', 'credit_limit', 'customer_code', 
                'company_name', 'tax_number', 'default_currency'
            )
        }),
        ('Sales & Language', {
            'fields': ('preferred_language', 'assigned_salesperson')
        }),
        ('Status & Loyalty', {
            'fields': (
                'is_active', 'is_vip', 'position', 'loyalty_points',
                'preferred_payment_method', 'last_order_date', 'notes'
            )
        }),
        ('Statistics', {
            'fields': ('total_due_display', 'total_orders_display', 'lifetime_value_display'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['loyalty_points', 'total_due_display', 'total_orders_display', 'lifetime_value_display']
    
    class Media:
        js = ('js/dependent_dropdowns.js', 'js/duplicate_confirmation.js')
    
    def pricing_tier_colored(self, obj):
        colors = {
            'retail': '#28a745',
            'wholesale': '#fd7e14',
            'distributor': '#dc3545',
            'special': '#6f42c1',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.pricing_tier, '#000'),
            obj.get_pricing_tier_display()
        )
    pricing_tier_colored.short_description = "Tier (colored)"
    
    def total_due_display(self, obj):
        return f"{obj.total_due:,.2f}"
    total_due_display.short_description = "Total Due"

    def total_orders_display(self, obj):
        return obj.total_orders
    total_orders_display.short_description = "Total Orders"

    def lifetime_value_display(self, obj):
        return f"{obj.lifetime_value:,.2f}"
    lifetime_value_display.short_description = "Lifetime Value"

    actions = ['mark_as_vip', 'remove_vip_status', 'set_retail_pricing', 'set_wholesale_pricing', 'set_distributor_pricing']

    def mark_as_vip(self, request, queryset):
        queryset.update(is_vip=True)
        self.message_user(request, f"{queryset.count()} customers marked as VIP.")
    mark_as_vip.short_description = "Mark selected as VIP"

    def remove_vip_status(self, request, queryset):
        queryset.update(is_vip=False)
        self.message_user(request, f"VIP status removed from {queryset.count()} customers.")
    remove_vip_status.short_description = "Remove VIP status"
    
    def set_retail_pricing(self, request, queryset):
        queryset.update(pricing_tier='retail', custom_discount_percentage=None, custom_price_list=None)
        self.message_user(request, f"{queryset.count()} customers set to Retail pricing.")
    set_retail_pricing.short_description = "Set pricing tier to Retail"
    
    def set_wholesale_pricing(self, request, queryset):
        queryset.update(pricing_tier='wholesale', custom_discount_percentage=None, custom_price_list=None)
        self.message_user(request, f"{queryset.count()} customers set to Wholesale pricing.")
    set_wholesale_pricing.short_description = "Set pricing tier to Wholesale"
    
    def set_distributor_pricing(self, request, queryset):
        queryset.update(pricing_tier='distributor', custom_discount_percentage=None, custom_price_list=None)
        self.message_user(request, f"{queryset.count()} customers set to Distributor pricing.")
    set_distributor_pricing.short_description = "Set pricing tier to Distributor"
    
    def save_model(self, request, obj, form, change):
        try:
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            if e.message == 'DUPLICATE_EMAIL':
                request.session['pending_customer_data'] = form.cleaned_data
                request.session['pending_customer_instance'] = obj.pk if obj.pk else None
                return redirect('admin:sales_customer_confirm_duplicate')
            else:
                raise
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('confirm-duplicate/', 
                 self.admin_site.admin_view(self.confirm_duplicate_view),
                 name='sales_customer_confirm_duplicate'),
        ]
        return custom_urls + urls
    
    def confirm_duplicate_view(self, request):
        if request.method == 'POST':
            if 'confirm' in request.POST:
                data = request.session.get('pending_customer_data')
                instance_id = request.session.get('pending_customer_instance')
                
                if data:
                    data['confirm_duplicate'] = 'on'
                
                if instance_id:
                    customer = Customer.objects.get(pk=instance_id)
                    form = CustomerAdminForm(data, instance=customer)
                else:
                    form = CustomerAdminForm(data)
                
                if form.is_valid():
                    customer = form.save()
                    messages.success(request, f'Customer "{customer.full_name}" saved successfully (duplicate email confirmed).')
                else:
                    messages.error(request, 'Error saving customer. Please check the form.')
                
                if 'pending_customer_data' in request.session:
                    del request.session['pending_customer_data']
                if 'pending_customer_instance' in request.session:
                    del request.session['pending_customer_instance']
                
                return redirect('admin:sales_customer_changelist')
            else:
                messages.warning(request, 'Save cancelled.')
                
                if 'pending_customer_data' in request.session:
                    del request.session['pending_customer_data']
                if 'pending_customer_instance' in request.session:
                    del request.session['pending_customer_instance']
                
                return redirect('admin:sales_customer_changelist')
        
        return render(request, 'admin/duplicate_confirmation.html', {
            'title': 'Confirm Duplicate Customer',
            'object_type': 'Customer',
            'object_name': request.session.get('pending_customer_data', {}).get('email', 'Unknown'),
            'back_url': '/admin/sales/customer/',
        })


# ============= SALES ORDER ADMIN =============

@admin.register(SalesOrder)
class SalesOrderAdmin(ERPAdminMixin, ConfigurableExportMixin, SalesDashboardMixin, admin.ModelAdmin):
    export_fields = [
        'order_number', 'customer__full_name', 'status', 'order_date',
        'total_amount', 'tax_amount', 'discount_amount', 'warehouse__name', 'created_at',
    ]
    export_methods = {
        'customer__full_name': lambda obj: obj.customer.full_name if obj.customer else '',
        'status': lambda obj: obj.get_status_display(),
        'warehouse__name': lambda obj: obj.warehouse.name if obj.warehouse else '',
    }
    export_sheet_name = 'Sales Orders'

    list_display = (
        'order_number', 'customer', 'pricing_tier_display', 'status', 'order_date', 
        'total_amount_display', 'delivery_status', 'action_buttons'
    )
    list_filter = ('status', 'order_date', 'warehouse', 'customer__pricing_tier')
    search_fields = ('order_number', 'customer__full_name', 'customer__email')
    inlines = [SalesOrderLineInline]
    readonly_fields = ['order_number', 'created_at', 'updated_at', 'total_amount_display', 'pricing_summary', 'order_date']
    date_hierarchy = 'order_date'

    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'customer', 'warehouse', 'order_date', 'expected_delivery_date', 'status')
        }),
        ('Pricing Information', {
            'fields': ('pricing_summary',),
            'description': 'Prices are calculated based on customer\'s pricing tier'
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at')
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in ['completed', 'cancelled', 'invoiced']:
            return [f.name for f in self.model._meta.fields]
        return self.readonly_fields

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('confirm/<int:order_id>/',
                 self.admin_site.admin_view(self.process_confirm),
                 name='salesorder-confirm'),
            path('cancel/<int:order_id>/',
                 self.admin_site.admin_view(self.process_cancel),
                 name='salesorder-cancel'),
            path('deliver/<int:order_id>/',
                 self.admin_site.admin_view(self.process_delivery),
                 name='salesorder-deliver'),
            path('invoice/<int:order_id>/',
                 self.admin_site.admin_view(self.create_invoice),
                 name='salesorder-invoice'),
        ]
        return custom_urls + urls

    def pricing_tier_display(self, obj):
        if obj.customer:
            colors = {
                'retail': '#28a745',
                'wholesale': '#fd7e14',
                'distributor': '#dc3545',
                'special': '#6f42c1',
            }
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                colors.get(obj.customer.pricing_tier, '#000'),
                obj.customer.get_pricing_tier_display()
            )
        return "-"
    pricing_tier_display.short_description = "Pricing Tier"
    
    def pricing_summary(self, obj):
        if obj.customer:
            lines = []
            for line in obj.lines.all()[:3]:
                lines.append(f"{line.product.name}: ${line.price}")
            
            summary = f"<strong>Customer:</strong> {obj.customer.display_name}<br>"
            summary += f"<strong>Pricing Tier:</strong> {obj.customer.get_pricing_tier_display()}<br>"
            
            if obj.customer.custom_discount_percentage:
                summary += f"<strong>Custom Discount:</strong> {obj.customer.custom_discount_percentage}%<br>"
            
            if lines:
                summary += f"<strong>Sample prices:</strong> {', '.join(lines)}"
            
            return format_html(summary)
        return "-"
    pricing_summary.short_description = "Pricing Summary"

    def total_amount_display(self, obj):
        return format_html('<b>{}</b>', obj.total_amount)
    total_amount_display.short_description = "Total"

    def delivery_status(self, obj):
        if obj.status == 'completed':
            return mark_safe('<span style="color: green;">✓ Fully Delivered</span>')
        elif obj.status == 'partial':
            total_qty = sum(l.quantity for l in obj.lines.all())
            return format_html('<span style="color: orange;">⏳ Partial ({}/{})</span>',
                               obj.total_delivered, total_qty)
        elif obj.status == 'confirmed':
            return mark_safe('<span style="color: blue;">⌛ Pending</span>')
        return "-"
    delivery_status.short_description = "Delivery"

    def action_buttons(self, obj):
        buttons = []
        if obj.status == 'draft':
            buttons.append(f'<a class="button" href="confirm/{obj.id}/">✅ Confirm</a>')
            buttons.append(f'<a class="button" href="cancel/{obj.id}/">❌ Cancel</a>')
        elif obj.status == 'confirmed':
            buttons.append(f'<a class="button" href="deliver/{obj.id}/">📦 Deliver</a>')
            buttons.append(f'<a class="button" href="cancel/{obj.id}/">❌ Cancel</a>')
            if not hasattr(obj, 'sales_invoice'):
                buttons.append(f'<a class="button" href="invoice/{obj.id}/">💰 Create Invoice</a>')
        elif obj.status == 'partial':
            buttons.append(f'<a class="button" href="deliver/{obj.id}/">📦 Continue Delivery</a>')
        
        return mark_safe(' '.join(buttons)) if buttons else "-"
    action_buttons.short_description = 'Actions'

    @transaction.atomic
    def process_confirm(self, request, order_id):
        order = SalesOrder.objects.get(pk=order_id)
        try:
            order.confirm()
            self.message_user(request, f"Order {order.order_number} confirmed successfully.", messages.SUCCESS)
        except ValidationError as e:
            self.message_user(request, str(e), messages.ERROR)
        return redirect(f'../../{order_id}/change/')

    @transaction.atomic
    def process_cancel(self, request, order_id):
        order = SalesOrder.objects.get(pk=order_id)
        try:
            order.cancel()
            self.message_user(request, f"Order {order.order_number} cancelled.", messages.SUCCESS)
        except ValidationError as e:
            self.message_user(request, str(e), messages.ERROR)
        return redirect(f'../../{order_id}/change/')

    def process_delivery(self, request, order_id):
        order = SalesOrder.objects.get(pk=order_id)
        
        if order.status not in ['confirmed', 'partial']:
            self.message_user(request, "Only confirmed or partially delivered orders can receive deliveries.", messages.ERROR)
            return redirect(f'../../{order_id}/change/')

        if request.method == 'POST':
            form = DeliveryForm(request.POST, order=order)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        for line in order.lines.all():
                            field_name = f'line_{line.id}'
                            qty = form.cleaned_data.get(field_name, 0)
                            if qty and qty > 0:
                                order.deliver_line(line.id, qty)
                    self.message_user(request, "Delivery processed successfully.", messages.SUCCESS)
                    return redirect(f'../../{order_id}/change/')
                except ValidationError as e:
                    self.message_user(request, str(e), messages.ERROR)
        else:
            form = DeliveryForm(order=order)

        context = {
            **self.admin_site.each_context(request),
            'title': f'Process Delivery - {order.order_number}',
            'order': order,
            'form': form,
        }
        return render(request, 'admin/sales/delivery_form.html', context)

    def create_invoice(self, request, order_id):
        order = SalesOrder.objects.get(pk=order_id)
        
        if hasattr(order, 'sales_invoice'):
            self.message_user(request, "Invoice already exists for this order.", messages.ERROR)
            return redirect(f'../../{order_id}/change/')

        try:
            with transaction.atomic():
                due_date = timezone.now().date() + timezone.timedelta(days=30)
                invoice = SalesInvoice.objects.create(
                    order=order,
                    customer=order.customer,
                    due_date=due_date,
                    total_amount=order.total_amount
                )
                self.message_user(request, f"Invoice {invoice.invoice_number} created successfully.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error creating invoice: {str(e)}", messages.ERROR)
        
        return redirect(f'../../{order_id}/change/')


# ============= SALES INVOICE ADMIN =============

@admin.register(SalesInvoice)
class SalesInvoiceAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = [
        'invoice_number', 'order', 'customer_pricing_display', 'invoice_date', 
        'due_date', 'total_amount_display', 'amount_paid_display', 
        'balance_display', 'status_colored'
    ]
    list_filter = ['status', 'invoice_date', 'due_date', 'customer__pricing_tier']
    search_fields = ['invoice_number', 'customer__full_name', 'order__order_number']
    readonly_fields = ['invoice_number', 'created_at', 'updated_at', 'pricing_info', 'invoice_date']
    inlines = [PaymentInline]
    date_hierarchy = 'invoice_date'

    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'order', 'customer', 'invoice_date', 'due_date', 'status')
        }),
        ('Pricing Information', {
            'fields': ('pricing_info',),
            'description': 'Pricing details based on customer tier'
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'amount_paid')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )

    def customer_pricing_display(self, obj):
        colors = {
            'retail': '#28a745',
            'wholesale': '#fd7e14',
            'distributor': '#dc3545',
            'special': '#6f42c1',
        }
        return format_html(
            '{}<br><small style="color: {};">{}</small>',
            obj.customer.display_name,
            colors.get(obj.customer.pricing_tier, '#000'),
            obj.customer.get_pricing_tier_display()
        )
    customer_pricing_display.short_description = "Customer"
    
    def pricing_info(self, obj):
        if obj.customer:
            info = f"<strong>Pricing Tier:</strong> {obj.customer.get_pricing_tier_display()}<br>"
            if obj.customer.custom_discount_percentage:
                info += f"<strong>Custom Discount:</strong> {obj.customer.custom_discount_percentage}%<br>"
            info += f"<strong>Order Total:</strong> ${obj.total_amount}<br>"
            info += f"<strong>Based on prices from:</strong> {obj.order.order_number}"
            return format_html(info)
        return "-"
    pricing_info.short_description = "Pricing Details"

    def total_amount_display(self, obj):
        return format_html('<b>{:,.2f}</b>', obj.total_amount)
    total_amount_display.short_description = "Total"

    def amount_paid_display(self, obj):
        return format_html('{:,.2f}', obj.amount_paid)
    amount_paid_display.short_description = "Paid"

    def balance_display(self, obj):
        balance = obj.balance_due
        if balance > 0:
            return format_html('<span style="color: red;">{:,.2f}</span>', balance)
        return format_html('<span style="color: green;">0.00</span>')
    balance_display.short_description = "Balance"

    def status_colored(self, obj):
        colors = {
            'draft': 'gray',
            'unpaid': 'red',
            'partial': 'orange',
            'paid': 'green',
            'overdue': 'darkred',
            'cancelled': 'gray',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_colored.short_description = "Status"

    actions = ['mark_as_paid']

    def mark_as_paid(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.status != 'paid':
                invoice.amount_paid = invoice.total_amount
                invoice.status = 'paid'
                invoice.save()
                updated += 1
        self.message_user(request, f"{updated} invoices marked as paid.")
    mark_as_paid.short_description = "Mark selected as paid"


# ============= PAYMENT ADMIN =============

@admin.register(Payment)
class PaymentAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['invoice', 'amount', 'payment_method', 'payment_date', 'received_by']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['invoice__invoice_number', 'reference']
    readonly_fields = ['payment_date']