"""
config_settings/admin.py  —  FULLY UPDATED
============================================
Synced with config_settings_models_IMPROVED.py

Changes from original:
  FIX 1  — CurrencyAdmin: format_example called obj.format() → now obj.format_amount()
  FIX 2  — CurrencyAdmin: set_as_base action had race condition → wrapped in transaction
  FIX 3  — ERPSettingsAdmin: fieldsets updated for slimmed-down ERPSettings model
  FIX 4  — ModuleStatusAdmin: status_indicator now uses is_active property (checks expiry)
  FIX 5  — PricingConfigAdmin: added base_currency, prices_include_tax, rounding_rule

  NEW 1  — CompanyProfileAdmin        (split from ERPSettings)
  NEW 2  — DocumentNumberingAdmin     (split from ERPSettings, with test-number action)
  NEW 3  — SettingsChangeLogAdmin     (read-only audit log viewer)
  NEW 4  — ExchangeRateHistoryAdmin   (standalone admin for rate history)
  NEW 5  — Staleness warning on CurrencyAdmin list display
  NEW 6  — Expiring-soon warning on ModuleStatusAdmin
"""

from django.contrib import admin
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html, mark_safe, mark_safe
from django.utils import timezone
from django.shortcuts import redirect
from django.contrib import messages

from .models import (
    ERPSettings,
    CompanyProfile,
    DocumentNumberingConfig,
    ModuleStatus,
    PricingConfig,
    Currency,
    ExchangeRateHistory,
    SettingsChangeLog,
)


# ===========================================================================
# INLINE — Exchange Rate History (used inside CurrencyAdmin)
# ===========================================================================

class ExchangeRateHistoryInline(admin.TabularInline):
    model = ExchangeRateHistory
    extra = 0
    # FIX: all fields are read-only — this is an audit log, not editable
    readonly_fields = ('date', 'exchange_rate', 'note')
    fields = ('date', 'exchange_rate', 'note')
    can_delete = False
    max_num = 15
    ordering = ('-date',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ===========================================================================
# CURRENCY ADMIN  (updated)
# ===========================================================================

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'symbol', 'exchange_rate',
        'is_base', 'is_active',
        'staleness_display',   # NEW 5 — shows stale warning
        'status_display',
        'rates_last_updated',
    )
    list_filter = ('is_base', 'is_active')
    search_fields = ('code', 'name')
    list_editable = ('exchange_rate', 'is_active')
    readonly_fields = (
        'created_at', 'updated_at',
        'format_example',       # method
        'staleness_display',    # method
        'rates_last_updated',   # auto-stamped in model.save()
    )
    inlines = [ExchangeRateHistoryInline]
    list_per_page = 25
    actions = ['set_as_base', 'update_rates_from_api']

    fieldsets = (
        ('Basic Info', {
            'fields': ('code', 'name', 'symbol', 'is_base', 'is_active')
        }),
        ('Exchange Rate', {
            'fields': ('exchange_rate', 'rate_update_source',    # NEW — source tracking
                       'rates_last_updated', 'staleness_display'),
            'description': 'Set exchange rate relative to base currency (base = 1.0)'
        }),
        ('Formatting', {
            'fields': (
                'decimal_places', 'decimal_separator',
                'thousand_separator', 'symbol_position',
            ),
            'classes': ('collapse',)
        }),
        ('Format Preview', {
            'fields': ('format_example',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # ------------------------------------------------------------------
    # Display methods
    # ------------------------------------------------------------------

    def status_display(self, obj):
        # FIX BUG 1: format_html() with no {} placeholders raises TypeError.
        # Static HTML strings must use mark_safe() instead.
        if obj.is_base:
            return mark_safe('<span style="color:#b8860b;font-weight:bold;">⭐ BASE</span>')
        elif obj.is_active:
            return mark_safe('<span style="color:green;">✅ Active</span>')
        return mark_safe('<span style="color:red;">❌ Inactive</span>')
    status_display.short_description = 'Status'
    # FIX BUG 2: admin_order_field must be a real model field, not another method.
    status_display.admin_order_field = 'is_active'

    def staleness_display(self, obj):
        """NEW 5 — Visual staleness warning using is_rate_stale property."""
        if obj.is_base:
            # FIX BUG 1: static string → mark_safe
            return mark_safe('<span style="color:gray;">— (base)</span>')
        if obj.is_rate_stale:
            last = obj.rates_last_updated
            last_str = last.strftime('%Y-%m-%d %H:%M') if last else 'Never'
            # format_html IS correct here — last_str is a dynamic value
            return format_html(
                '<span style="color:orange;font-weight:bold;">'
                '⚠️ Stale (last: {})</span>', last_str
            )
        return mark_safe('<span style="color:green;">✅ Fresh</span>')
    staleness_display.short_description = 'Rate Freshness'
    staleness_display.admin_order_field = 'rates_last_updated'

    def format_example(self, obj):
        """FIX 1 — was calling obj.format() which doesn't exist → now obj.format_amount()"""
        try:
            return obj.format_amount(1234567.89)
        except Exception as e:
            return f"Error: {e}"
    format_example.short_description = 'Format Example (1,234,567.89)'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def set_as_base(self, request, queryset):
        """FIX 2 — original had race condition; now uses transaction + exclude(pk)."""
        if queryset.count() != 1:
            self.message_user(
                request, "❌ Select exactly one currency to set as base.", level='ERROR'
            )
            return

        currency = queryset.first()

        with transaction.atomic():
            Currency.objects.exclude(pk=currency.pk).filter(
                is_base=True
            ).update(is_base=False)
            currency.is_base = True
            currency.exchange_rate = 1.0
            currency.save()

        self.message_user(
            request, f"✅ {currency.code} set as base currency successfully."
        )
    set_as_base.short_description = "⭐ Set selected as base currency"

    def update_rates_from_api(self, request, queryset):
        """Placeholder — hook in your exchange rate API here."""
        self.message_user(
            request,
            "🔄 Rate update from API is not yet configured. "
            "Update rates manually or integrate an exchange rate provider.",
            level='WARNING'
        )
    update_rates_from_api.short_description = "🔄 Update rates from API"


# ===========================================================================
# EXCHANGE RATE HISTORY ADMIN  (standalone — NEW)
# ===========================================================================

@admin.register(ExchangeRateHistory)
class ExchangeRateHistoryAdmin(admin.ModelAdmin):
    """NEW 4 — Standalone admin so you can view all historical rates easily."""
    list_display = ('currency', 'date', 'exchange_rate', 'note')
    list_filter = ('currency', 'date')
    search_fields = ('currency__code', 'currency__name', 'note')
    readonly_fields = ('currency', 'date', 'exchange_rate', 'note')
    date_hierarchy = 'date'
    ordering = ('-date',)
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ===========================================================================
# COMPANY PROFILE ADMIN  (NEW 1 — split from ERPSettings)
# ===========================================================================

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    """NEW 1 — CompanyProfile was previously buried inside ERPSettings."""

    fieldsets = (
        ('🏢 Company Identity', {
            'fields': ('name', 'logo', 'website')
        }),
        ('📞 Contact Information', {
            'fields': ('address', 'phone', 'email')
        }),
        ('📜 Registration', {
            'fields': ('tax_id', 'registration_number')
        }),
        ('📅 Fiscal Year', {
            'fields': ('fiscal_year_start', 'fiscal_year_end'),
            'description': (
                'Set the fiscal year dates. End must be after start. '
                'Use the get_current_fiscal_year() method programmatically.'
            )
        }),
        ('🕐 Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at', 'fiscal_year_display')

    def fiscal_year_display(self, obj):
        fy = obj.get_current_fiscal_year()
        if not fy:
            return "Not configured"
        return format_html(
            '<strong>{}</strong> to <strong>{}</strong>',
            fy[0].strftime('%d %b %Y'),
            fy[1].strftime('%d %b %Y')
        )
    fiscal_year_display.short_description = 'Current Fiscal Year'

    def has_add_permission(self, request):
        return not CompanyProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Redirect list view directly to the single record."""
        profile, _ = CompanyProfile.objects.get_or_create(pk=1)
        return redirect(
            reverse('admin:config_settings_companyprofile_change', args=[profile.pk])
        )


# ===========================================================================
# DOCUMENT NUMBERING ADMIN  (NEW 2 — split from ERPSettings)
# ===========================================================================

@admin.register(DocumentNumberingConfig)
class DocumentNumberingAdmin(admin.ModelAdmin):
    """NEW 2 — Document numbering was previously buried inside ERPSettings."""

    fieldsets = (
        ('🧾 Invoice Numbering', {
            'fields': ('invoice_numbering', 'invoice_prefix', 'invoice_next_number'),
        }),
        ('🛒 Sales Order Numbering', {
            'fields': ('sales_order_numbering', 'sales_order_prefix', 'sales_order_next_number'),
        }),
        ('📦 Purchase Order Numbering', {
            'fields': ('purchase_order_numbering', 'purchase_order_prefix', 'purchase_order_next_number'),
        }),
        ('👤 Customer Numbering', {
            'fields': ('customer_numbering', 'customer_prefix', 'customer_next_number'),
        }),
        ('🏭 Vendor Numbering', {
            'fields': ('vendor_numbering', 'vendor_prefix', 'vendor_next_number'),
        }),
        ('⚙️ Global Settings', {
            'fields': ('pad_length',),
            'description': 'pad_length controls zero-padding: 4 = 0001, 6 = 000001'
        }),
        ('👁️ Preview', {
            'fields': ('number_preview',),
            'classes': ('collapse',),
            'description': 'Shows what the next number will look like for each type.'
        }),
    )

    readonly_fields = ('number_preview',)
    actions = ['test_generate_numbers']

    def number_preview(self, obj):
        """Show a live preview of what each next number looks like."""
        if not obj.pk:
            return "Save first to see preview"

        rows = []
        for doc_type in ('invoice', 'sales_order', 'purchase_order', 'customer', 'vendor'):
            prefix = getattr(obj, f'{doc_type}_prefix', '')
            method = getattr(obj, f'{doc_type}_numbering', 'yearly')
            seq = getattr(obj, f'{doc_type}_next_number', 1)
            seq_str = str(seq).zfill(obj.pad_length)

            from datetime import date
            today = date.today()
            if method == 'sequential':
                preview = f"{prefix}-{seq_str}"
            elif method == 'yearly':
                preview = f"{prefix}-{today.year}-{seq_str}"
            else:  # monthly
                preview = f"{prefix}-{today.strftime('%Y%m')}-{seq_str}"

            rows.append(
                f'<tr>'
                f'<td style="padding:4px 12px;font-weight:bold;">{doc_type.replace("_", " ").title()}</td>'
                f'<td style="padding:4px 12px;font-family:monospace;color:#1a73e8;">{preview}</td>'
                f'</tr>'
            )

        return format_html(
            '<table style="border-collapse:collapse;">'
            '<tr style="background:#f0f0f0;">'
            '<th style="padding:4px 12px;text-align:left;">Document Type</th>'
            '<th style="padding:4px 12px;text-align:left;">Next Number</th>'
            '</tr>'
            '{}'
            '</table>',
            format_html(''.join(rows))
        )
    number_preview.short_description = 'Next Number Preview'

    def test_generate_numbers(self, request, queryset):
        """
        Action to test the generate_number() method without permanently incrementing.
        Shows what numbers WOULD be generated — does not save to DB.
        """
        config = queryset.first()
        previews = []
        for doc_type in ('invoice', 'sales_order', 'purchase_order', 'customer', 'vendor'):
            prefix = getattr(config, f'{doc_type}_prefix', '')
            method = getattr(config, f'{doc_type}_numbering', 'yearly')
            seq = getattr(config, f'{doc_type}_next_number', 1)
            seq_str = str(seq).zfill(config.pad_length)

            from datetime import date
            today = date.today()
            if method == 'sequential':
                preview = f"{prefix}-{seq_str}"
            elif method == 'yearly':
                preview = f"{prefix}-{today.year}-{seq_str}"
            else:
                preview = f"{prefix}-{today.strftime('%Y%m')}-{seq_str}"

            previews.append(f"{doc_type}: {preview}")

        self.message_user(
            request,
            "📋 Next numbers would be: " + " | ".join(previews)
        )
    test_generate_numbers.short_description = "👁️ Preview next document numbers"

    def has_add_permission(self, request):
        return not DocumentNumberingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        config, _ = DocumentNumberingConfig.objects.get_or_create(pk=1)
        return redirect(
            reverse('admin:config_settings_documentnumberingconfig_change', args=[config.pk])
        )


# ===========================================================================
# ERP SETTINGS ADMIN  (FIX 3 — slimmed down to match new model)
# ===========================================================================

@admin.register(ERPSettings)
class ERPSettingsAdmin(admin.ModelAdmin):
    """
    FIX 3 — Updated fieldsets to match slimmed-down ERPSettings.
    Company info → CompanyProfileAdmin
    Numbering    → DocumentNumberingAdmin
    """

    fieldsets = (
        ('🚀 Setup Status', {
            'fields': ('setup_completed', 'setup_completed_at', 'first_product_added'),
            'classes': ('collapse',),
        }),
        ('💱 Default Currency & Formatting', {
            'fields': (
                'default_currency',
                'currency_position',
                'thousand_separator',
                'decimal_separator',
                'price_decimals',
                'cost_decimals',
            ),
            'description': (
                '⚠️ price_decimals and cost_decimals are LOCKED after first product is added.'
            )
        }),
        ('📅 Date & Time Format', {
            'fields': ('date_format', 'time_format', 'timezone_name'),
        }),
        ('📦 Inventory Global Rules', {
            'fields': (
                'allow_negative_inventory',
                'default_reorder_level',
                'low_stock_threshold_percentage',
            ),
        }),
        ('🏷️ SKU Generation', {
            'fields': ('sku_pattern', 'sku_length'),
            'description': '⚠️ sku_pattern is LOCKED after first product is added.',
        }),
        ('🔗 Related Settings', {
            'fields': ('company_profile_link', 'numbering_link'),
            'description': 'Company info and document numbering are managed separately.',
        }),
        ('📊 Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = (
        'created_at', 'updated_at',
        'setup_completed', 'setup_completed_at',
        'company_profile_link', 'numbering_link',
    )

    def get_readonly_fields(self, request, obj=None):
        """Lock price_decimals, cost_decimals, sku_pattern after first product."""
        readonly = list(self.readonly_fields)
        if obj and obj.first_product_added:
            readonly.extend(['price_decimals', 'cost_decimals', 'sku_pattern', 'sku_length'])
        return readonly

    def company_profile_link(self, obj):
        """Quick link to CompanyProfile admin."""
        try:
            profile = CompanyProfile.objects.get(pk=1)
            url = reverse('admin:config_settings_companyprofile_change', args=[profile.pk])
            return format_html('<a href="{}" class="button">🏢 Edit Company Profile</a>', url)
        except CompanyProfile.DoesNotExist:
            url = reverse('admin:config_settings_companyprofile_add')
            return format_html('<a href="{}" class="button">➕ Create Company Profile</a>', url)
    company_profile_link.short_description = 'Company Profile'

    def numbering_link(self, obj):
        """Quick link to DocumentNumberingConfig admin."""
        try:
            config = DocumentNumberingConfig.objects.get(pk=1)
            url = reverse('admin:config_settings_documentnumberingconfig_change', args=[config.pk])
            return format_html('<a href="{}" class="button">📋 Edit Document Numbering</a>', url)
        except DocumentNumberingConfig.DoesNotExist:
            url = reverse('admin:config_settings_documentnumberingconfig_add')
            return format_html('<a href="{}" class="button">➕ Create Numbering Config</a>', url)
    numbering_link.short_description = 'Document Numbering'

    def has_add_permission(self, request):
        return not ERPSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj, _ = ERPSettings.objects.get_or_create(pk=1)
        return redirect(
            reverse('admin:config_settings_erpsettings_change', args=[settings_obj.pk])
        )


# ===========================================================================
# PRICING CONFIG ADMIN  (FIX 5 — added new fields)
# ===========================================================================

@admin.register(PricingConfig)
class PricingConfigAdmin(admin.ModelAdmin):
    """FIX 5 — Added base_currency, prices_include_tax, rounding_rule."""

    fieldsets = (
        ('💰 Pricing Model', {
            'fields': ('pricing_model', 'base_currency'),
            'description': 'base_currency is the currency used for all base price calculations.'
        }),
        ('🏷️ Price List Names', {
            'fields': (
                'default_retail_name',
                'default_wholesale_name',
                'default_distributor_name',
            ),
            'description': 'Default names used when auto-creating price lists.'
        }),
        ('🧮 Calculation Rules', {
            'fields': ('prices_include_tax', 'rounding_rule'),
            'description': (
                'prices_include_tax: if True, displayed prices already include tax. '
                'rounding_rule: controls how calculated prices are rounded.'
            )
        }),
    )

    readonly_fields = ('pricing_model_display',)

    def pricing_model_display(self, obj):
        if obj.pricing_model == 'single':
            return format_html(
                '<span style="color:blue;">📌 Single Price</span> — '
                'all customers see the same price.'
            )
        return format_html(
            '<span style="color:green;">📊 Multi-Tier</span> — '
            'retail / wholesale / distributor prices are separate.'
        )
    pricing_model_display.short_description = 'Active Pricing Mode'

    def has_add_permission(self, request):
        return not PricingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        config, _ = PricingConfig.objects.get_or_create(pk=1)
        return redirect(
            reverse('admin:config_settings_pricingconfig_change', args=[config.pk])
        )


# ===========================================================================
# MODULE STATUS ADMIN  (FIX 4 — expiry-aware + expiring-soon warning)
# ===========================================================================

@admin.register(ModuleStatus)
class ModuleStatusAdmin(admin.ModelAdmin):
    """FIX 4 — status_indicator now uses is_active (checks expiry_date)."""

    list_display = (
        'module_display', 'is_enabled',
        'status_indicator',     # FIX 4 — uses is_active property
        'expiry_display',       # NEW 6 — expiry warning
        'notes_preview',
    )
    list_filter = ('is_enabled',)
    search_fields = ('module', 'notes')
    list_editable = ('is_enabled',)
    list_per_page = 20

    fieldsets = (
        ('Module', {
            'fields': ('module', 'is_enabled', 'notes')
        }),
        ('License', {
            'fields': ('license_key', 'expiry_date'),
            'description': (
                'If expiry_date is set, the module will automatically become '
                'inactive after that date even if is_enabled is True.'
            ),
            'classes': ('collapse',)
        }),
    )

    def module_display(self, obj):
        return obj.get_module_display()
    module_display.short_description = 'Module'
    module_display.admin_order_field = 'module'

    def status_indicator(self, obj):
        """
        FIX 4 — Uses obj.is_active property instead of obj.is_enabled.
        Catches cases where is_enabled=True but expiry_date has passed.
        """
        if obj.is_active:
            return mark_safe('<span style="color:green;font-weight:bold;">✅ Active</span>')
        # Distinguish between manually disabled vs expired
        if obj.is_enabled and obj.expiry_date:
            from datetime import date
            if obj.expiry_date < date.today():
                return format_html(
                    '<span style="color:orange;font-weight:bold;">⏰ Expired</span>'
                )
        return mark_safe('<span style="color:red;font-weight:bold;">❌ Disabled</span>')
    status_indicator.short_description = 'Status'

    def expiry_display(self, obj):
        """NEW 6 — Shows expiry date with colour-coded warning."""
        if not obj.expiry_date:
            return mark_safe('<span style="color:gray;">—</span>')

        from datetime import date
        today = date.today()
        days_left = (obj.expiry_date - today).days

        if days_left < 0:
            return format_html(
                '<span style="color:red;font-weight:bold;">⛔ Expired {}</span>',
                obj.expiry_date.strftime('%d %b %Y')
            )
        elif days_left <= 30:
            return format_html(
                '<span style="color:orange;font-weight:bold;">'
                '⚠️ Expires in {} days ({})</span>',
                days_left,
                obj.expiry_date.strftime('%d %b %Y')
            )
        return format_html(
            '<span style="color:green;">{}</span>',
            obj.expiry_date.strftime('%d %b %Y')
        )
    expiry_display.short_description = 'Expiry'
    expiry_display.admin_order_field = 'expiry_date'

    def notes_preview(self, obj):
        if not obj.notes:
            return mark_safe('<span style="color:gray;">—</span>')
        truncated = obj.notes[:60] + ('…' if len(obj.notes) > 60 else '')
        return truncated
    notes_preview.short_description = 'Notes'


# ===========================================================================
# SETTINGS CHANGE LOG ADMIN  (NEW 3 — full audit log viewer)
# ===========================================================================

@admin.register(SettingsChangeLog)
class SettingsChangeLogAdmin(admin.ModelAdmin):
    """NEW 3 — Read-only audit log for all settings changes."""

    list_display = (
        'changed_at_display', 'setting_type', 'field_name',
        'old_value_display', 'new_value_display',
        'changed_by', 'note'
    )
    list_filter = ('setting_type', 'changed_by', 'changed_at')
    search_fields = ('field_name', 'old_value', 'new_value', 'changed_by__username', 'note')
    readonly_fields = (
        'setting_type', 'setting_id', 'field_name',
        'old_value', 'new_value',
        'changed_by', 'changed_at', 'note'
    )
    date_hierarchy = 'changed_at'
    ordering = ('-changed_at',)
    list_per_page = 50

    fieldsets = (
        ('Change Details', {
            'fields': (
                'setting_type', 'setting_id', 'field_name',
                'old_value', 'new_value',
            )
        }),
        ('Who & When', {
            'fields': ('changed_by', 'changed_at', 'note')
        }),
    )

    def changed_at_display(self, obj):
        return obj.changed_at.strftime('%Y-%m-%d %H:%M')
    changed_at_display.short_description = 'Changed At'
    changed_at_display.admin_order_field = 'changed_at'

    def old_value_display(self, obj):
        if not obj.old_value:
            return mark_safe('<span style="color:gray;">—</span>')
        truncated = str(obj.old_value)[:40]
        return format_html(
            '<span style="color:#c0392b;">{}</span>', truncated
        )
    old_value_display.short_description = 'Old Value'

    def new_value_display(self, obj):
        if not obj.new_value:
            return mark_safe('<span style="color:gray;">—</span>')
        truncated = str(obj.new_value)[:40]
        return format_html(
            '<span style="color:#27ae60;font-weight:bold;">{}</span>', truncated
        )
    new_value_display.short_description = 'New Value'

    # Audit log is immutable
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False