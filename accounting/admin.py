from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django import forms
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Invoice, Bill, Payment, JournalEntry, JournalLine,
    Account, FiscalYear, FiscalPeriod, AccountingSettings, 
    ExchangeRate, AuditLog
)
from exports.mixins import ConfigurableExportMixin
from exports.column_config import ColumnConfigMixin
from rbac.admin_mixins import ERPAdminMixin


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ['payment_number', 'payment_date', 'status']
    fields = ['payment_number', 'amount', 'payment_method', 'payment_date', 'status']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 1
    fields = ['account', 'account_code', 'account_name', 'description', 'debit_credit', 'amount']
    readonly_fields = ['account_code', 'account_name']
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            kwargs["queryset"] = Account.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Invoice)
class InvoiceAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin):
    ALL_LIST_COLUMNS = [
        ('invoice_number', 'Invoice #'),
        ('customer_link', 'Customer'),
        ('invoice_date', 'Invoice Date'),
        ('due_date', 'Due Date'),
        ('net_amount', 'Net Amount'),
        ('amount_paid', 'Amount Paid'),
        ('balance_due', 'Balance Due'),
        ('status_colored', 'Status'),
    ]
    DEFAULT_COLUMNS = ['invoice_number', 'customer_link', 'invoice_date', 'due_date', 'net_amount', 'balance_due', 'status_colored']
    REQUIRED_COLUMNS = ['invoice_number']
    list_display = [
        'invoice_number', 'customer_link', 'invoice_date', 'due_date',
        'net_amount', 'amount_paid', 'balance_due', 'status_colored'
    ]
    list_filter = ['status', 'invoice_date', 'due_date']
    search_fields = ['invoice_number', 'customer__full_name']
    readonly_fields = ['invoice_number', 'created_at', 'updated_at', 'sent_date', 'paid_date']
    date_hierarchy = 'invoice_date'
    inlines = [PaymentInline]
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'sales_order', 'customer', 'invoice_date', 'due_date', 'status')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'tax_amount', 'discount_amount', 'net_amount', 'amount_paid')
        }),
        ('Additional Info', {
            'fields': ('notes', 'terms_conditions', 'sent_date', 'paid_date', 'created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('customer', 'sales_order')

    def customer_link(self, obj):
        if obj.customer:
            return format_html(
                '<a href="{}">{}</a>',
                reverse('admin:sales_customer_change', args=[obj.customer.id]),
                obj.customer.full_name
            )
        return "-"
    customer_link.short_description = "Customer"

    def status_colored(self, obj):
        colors = {
            'draft': 'gray',
            'sent': 'blue',
            'partial': 'orange',
            'paid': 'green',
            'overdue': 'darkred',
            'cancelled': 'gray',
            'void': 'gray',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_colored.short_description = "Status"


@admin.register(Bill)
class BillAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin):
    ALL_LIST_COLUMNS = [
        ('bill_number', 'Bill #'),
        ('vendor_link', 'Vendor'),
        ('bill_date', 'Bill Date'),
        ('due_date', 'Due Date'),
        ('net_amount', 'Net Amount'),
        ('amount_paid', 'Amount Paid'),
        ('balance_due', 'Balance Due'),
        ('status_colored', 'Status'),
    ]
    DEFAULT_COLUMNS = ['bill_number', 'vendor_link', 'bill_date', 'due_date', 'net_amount', 'balance_due', 'status_colored']
    REQUIRED_COLUMNS = ['bill_number']
    list_display = [
        'bill_number', 'vendor_link', 'bill_date', 'due_date',
        'net_amount', 'amount_paid', 'balance_due', 'status_colored'
    ]
    list_filter = ['status', 'bill_date', 'due_date']
    search_fields = ['bill_number', 'vendor__name']
    readonly_fields = ['bill_number', 'created_at', 'updated_at', 'paid_date']
    date_hierarchy = 'bill_date'
    inlines = [PaymentInline]

    fieldsets = (
        ('Bill Information', {
            'fields': ('bill_number', 'purchase_order', 'vendor', 'bill_date', 'due_date', 'status')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'tax_amount', 'discount_amount', 'net_amount', 'amount_paid')
        }),
        ('Additional Info', {
            'fields': ('notes', 'paid_date', 'created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vendor', 'purchase_order')

    def vendor_link(self, obj):
        if obj.vendor:
            return format_html(
                '<a href="{}">{}</a>',
                reverse('admin:purchasing_vendor_change', args=[obj.vendor.id]),
                obj.vendor.name
            )
        return "-"
    vendor_link.short_description = "Vendor"

    def status_colored(self, obj):
        colors = {
            'draft': 'gray',
            'received': 'blue',
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


@admin.register(Payment)
class PaymentAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin):
    ALL_LIST_COLUMNS = [
        ('payment_number', 'Payment #'),
        ('payment_type', 'Type'),
        ('related_document', 'Document'),
        ('amount', 'Amount'),
        ('payment_method', 'Method'),
        ('payment_date', 'Date'),
        ('status_colored', 'Status'),
    ]
    DEFAULT_COLUMNS = ['payment_number', 'payment_type', 'related_document', 'amount', 'payment_date', 'status_colored']
    REQUIRED_COLUMNS = ['payment_number']
    list_display = [
        'payment_number', 'payment_type', 'related_document', 'amount',
        'payment_method', 'payment_date', 'status_colored'
    ]
    list_filter = ['payment_type', 'payment_method', 'status', 'payment_date']
    search_fields = ['payment_number', 'reference', 'invoice__invoice_number', 'bill__bill_number']
    readonly_fields = ['payment_number', 'created_at']
    date_hierarchy = 'payment_date'

    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_number', 'payment_type', 'payment_method', 'status', 'payment_date')
        }),
        ('Amount Details', {
            'fields': ('amount', 'currency')
        }),
        ('Reference', {
            'fields': ('invoice', 'bill', 'reference', 'notes')
        }),
    )

    def related_document(self, obj):
        if obj.invoice:
            return format_html(
                'Invoice: <a href="{}">{}</a>',
                reverse('admin:accounting_invoice_change', args=[obj.invoice.id]),
                obj.invoice.invoice_number
            )
        elif obj.bill:
            return format_html(
                'Bill: <a href="{}">{}</a>',
                reverse('admin:accounting_bill_change', args=[obj.bill.id]),
                obj.bill.bill_number
            )
        return "-"
    related_document.short_description = "Related Document"

    def status_colored(self, obj):
        colors = {
            'pending': 'orange',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'gray',
            'refunded': 'purple',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_colored.short_description = "Status"


@admin.register(JournalEntry)
class JournalEntryAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin):
    ALL_LIST_COLUMNS = [
        ('entry_number', 'Entry #'),
        ('entry_date', 'Date'),
        ('journal_type', 'Type'),
        ('description_short', 'Description'),
        ('total_debits', 'Debits'),
        ('approval_status', 'Approval'),
        ('is_posted', 'Posted'),
    ]
    DEFAULT_COLUMNS = ['entry_number', 'entry_date', 'journal_type', 'description_short', 'total_debits', 'approval_status', 'is_posted']
    REQUIRED_COLUMNS = ['entry_number']
    list_display = [
        'entry_number', 'entry_date', 'journal_type',
        'description_short', 'total_debits', 'approval_status', 'is_posted'
    ]
    list_filter = ['journal_type', 'approval_status', 'is_posted', 'entry_date']
    search_fields = ['entry_number', 'description']
    readonly_fields = ['entry_number', 'created_at']
    inlines = [JournalLineInline]
    date_hierarchy = 'entry_date'
    
    fieldsets = (
        ('Journal Information', {
            'fields': ('entry_number', 'journal_type', 'entry_date', 'description')
        }),
        ('Status', {
            'fields': ('approval_status', 'is_posted', 'requires_approval')
        }),
        ('References', {
            'fields': ('invoice', 'bill', 'payment'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'invoice', 'bill', 'payment'
        )

    def description_short(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'


@admin.register(JournalLine)
class JournalLineAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['journal_entry', 'account', 'debit_credit', 'amount']
    list_filter = ['debit_credit']
    search_fields = ['account_code', 'account_name', 'description']


@admin.register(Account)
class AccountAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'currency', 'is_active']
    list_filter = ['type', 'is_active', 'currency']
    search_fields = ['code', 'name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Account Information', {
            'fields': ('code', 'name', 'type', 'parent', 'is_active', 'is_system')
        }),
        ('Financial', {
            'fields': ('opening_balance', 'opening_balance_date', 'currency')
        }),
        ('Bank Details', {
            'fields': ('bank_name', 'bank_account_number', 'bank_routing_number', 'bank_currency'),
            'classes': ('collapse',)
        }),
    )


@admin.register(FiscalYear)
class FiscalYearAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_closed']
    list_filter = ['is_closed']
    search_fields = ['name']


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['fiscal_year', 'period_number', 'period_type', 'start_date', 'end_date', 'is_closed']
    list_filter = ['period_type', 'is_closed', 'fiscal_year']
    search_fields = ['fiscal_year__name']


@admin.register(AccountingSettings)
class AccountingSettingsAdmin(ERPAdminMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        return not AccountingSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExchangeRate)
class ExchangeRateAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['from_currency', 'to_currency', 'rate', 'date']
    list_filter = ['from_currency', 'to_currency', 'date']


@admin.register(AuditLog)
class AuditLogAdmin(ERPAdminMixin, admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'content_type', 'object_id']
    list_filter = ['action', 'content_type', 'timestamp']
    search_fields = ['user__username', 'details']
    readonly_fields = ['timestamp', 'user', 'action', 'content_type', 'object_id']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False