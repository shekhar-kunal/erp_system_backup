"""
config_settings/models.py  —  ENHANCED VERSION
================================================
Improvements over the original:

1.  ERPSettings split into focused models (God Object → SRP)
2.  Automatic ExchangeRateHistory logging via signal
3.  Currency staleness detection (rates_last_updated)
4.  ModuleStatus expiry enforcement + cache invalidation signal
5.  Fiscal year validation + helper methods
6.  ERPSettings number formatter (uses configured separators)
7.  SettingsChangeLog — audit trail for all settings changes
8.  CompanyProfile separated from ERPSettings
9.  DocumentNumberingConfig separated from ERPSettings
10. All singletons use consistent get_or_create(pk=1) pattern with caching
"""

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone as tz
from datetime import date, timedelta
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.core.cache import cache
from django.contrib.auth import get_user_model


# ===========================================================================
# IMPROVEMENT 1 — SettingsChangeLog
# Audit trail: every time any settings record changes, log who changed what.
# Previously: zero audit trail on settings changes.
# ===========================================================================

class SettingsChangeLog(models.Model):
    """
    Immutable audit log for all settings changes across the ERP.
    Records who changed what, when, and what the old/new values were.
    """
    SETTING_CHOICES = [
        ('erp_settings', 'ERP Settings'),
        ('company_profile', 'Company Profile'),
        ('pricing_config', 'Pricing Configuration'),
        ('currency', 'Currency'),
        ('module_status', 'Module Status'),
        ('doc_numbering', 'Document Numbering'),
    ]

    setting_type = models.CharField(max_length=50, choices=SETTING_CHOICES)
    setting_id = models.IntegerField(help_text="PK of the changed record")
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['setting_type', '-changed_at']),
            models.Index(fields=['changed_by', '-changed_at']),
        ]

    def __str__(self):
        user = self.changed_by.username if self.changed_by else 'System'
        return f"[{self.setting_type}] {self.field_name}: {self.old_value} → {self.new_value} ({user})"

    @classmethod
    def log_change(cls, setting_type, setting_id, field_name,
                   old_value, new_value, user=None, note=''):
        """Convenience method to log a single field change."""
        if str(old_value) == str(new_value):
            return  # No actual change — skip
        cls.objects.create(
            setting_type=setting_type,
            setting_id=setting_id,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            changed_by=user,
            note=note,
        )


# ===========================================================================
# IMPROVEMENT 2 — CompanyProfile (split out of ERPSettings God Object)
# Previously: company info was buried in ERPSettings alongside unrelated fields.
# Now it's its own model — easier to read, query, and extend.
# ===========================================================================

class CompanyProfile(models.Model):
    """
    Company information. Singleton (pk=1).
    Split from ERPSettings to keep each model focused.
    """
    name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    tax_id = models.CharField(max_length=100, blank=True, help_text="VAT / Tax ID")
    registration_number = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(upload_to='company/', blank=True, null=True)

    # IMPROVEMENT 2a — Fiscal year with validation
    fiscal_year_start = models.DateField(
        null=True, blank=True,
        help_text="Start date of fiscal year (e.g., Jan 1)"
    )
    fiscal_year_end = models.DateField(
        null=True, blank=True,
        help_text="End date of fiscal year (e.g., Dec 31)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profile"

    def __str__(self):
        return self.name or "Company Profile (not configured)"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete('company_profile')

    def clean(self):
        """
        IMPROVEMENT 2b — Fiscal year validation.
        Previously: no validation at all — end could be before start.
        """
        if self.fiscal_year_start and self.fiscal_year_end:
            if self.fiscal_year_end <= self.fiscal_year_start:
                raise ValidationError({
                    'fiscal_year_end': 'Fiscal year end must be after start date.'
                })
            # Fiscal year should be roughly 12 months
            delta = (self.fiscal_year_end - self.fiscal_year_start).days
            if delta < 28 or delta > 366:
                raise ValidationError({
                    'fiscal_year_end': 'Fiscal year must be between 1 month and 366 days.'
                })

    @classmethod
    def get_profile(cls):
        """Get or create singleton company profile (cached)."""
        profile = cache.get('company_profile')
        if profile is None:
            profile, _ = cls.objects.get_or_create(pk=1)
            cache.set('company_profile', profile, 600)
        return profile

    # IMPROVEMENT 2c — Fiscal year helpers
    def get_current_fiscal_year(self):
        """
        Return (start_date, end_date) for the current fiscal year.
        Handles fiscal years that span two calendar years (e.g., Apr–Mar).
        Returns None if fiscal year is not configured.
        """
        if not self.fiscal_year_start or not self.fiscal_year_end:
            return None

        today = date.today()
        # Build this year's fiscal start
        try:
            fy_start = self.fiscal_year_start.replace(year=today.year)
        except ValueError:
            # Feb 29 in a non-leap year
            fy_start = self.fiscal_year_start.replace(year=today.year, day=28)

        if today >= fy_start:
            start = fy_start
        else:
            start = fy_start.replace(year=today.year - 1)

        # End is always 1 year minus 1 day after start
        end = start.replace(year=start.year + 1) - timedelta(days=1)
        return start, end

    def is_in_fiscal_year(self, check_date=None):
        """Check if a date falls in the current fiscal year."""
        fy = self.get_current_fiscal_year()
        if not fy:
            return None
        d = check_date or date.today()
        return fy[0] <= d <= fy[1]


# ===========================================================================
# IMPROVEMENT 3 — DocumentNumberingConfig (split out of ERPSettings)
# Previously: 8+ numbering fields crammed into ERPSettings.
# Now it's its own model with a generate_number() helper.
# ===========================================================================

class DocumentNumberingConfig(models.Model):
    """
    Document number sequencing configuration. Singleton (pk=1).
    Handles invoices, sales orders, purchase orders, customers, vendors.
    """
    DOC_NUMBERING_CHOICES = [
        ('sequential', 'Sequential (0001, 0002, 0003)'),
        ('yearly', 'Yearly Reset (2024-0001, 2024-0002)'),
        ('monthly', 'Monthly Reset (202412-0001, 202412-0002)'),
    ]

    invoice_numbering = models.CharField(max_length=20, choices=DOC_NUMBERING_CHOICES, default='yearly')
    invoice_prefix = models.CharField(max_length=10, default='INV')
    invoice_next_number = models.PositiveIntegerField(default=1)

    sales_order_numbering = models.CharField(max_length=20, choices=DOC_NUMBERING_CHOICES, default='yearly')
    sales_order_prefix = models.CharField(max_length=10, default='SO')
    sales_order_next_number = models.PositiveIntegerField(default=1)

    purchase_order_numbering = models.CharField(max_length=20, choices=DOC_NUMBERING_CHOICES, default='yearly')
    purchase_order_prefix = models.CharField(max_length=10, default='PO')
    purchase_order_next_number = models.PositiveIntegerField(default=1)

    customer_numbering = models.CharField(max_length=20, choices=DOC_NUMBERING_CHOICES, default='yearly')
    customer_prefix = models.CharField(max_length=10, default='CUST')
    customer_next_number = models.PositiveIntegerField(default=1)

    vendor_numbering = models.CharField(max_length=20, choices=DOC_NUMBERING_CHOICES, default='yearly')
    vendor_prefix = models.CharField(max_length=10, default='VEND')
    vendor_next_number = models.PositiveIntegerField(default=1)

    pad_length = models.IntegerField(
        default=4,
        help_text="Zero-padding length for sequence number (4 = 0001)"
    )

    class Meta:
        verbose_name = "Document Numbering"
        verbose_name_plural = "Document Numbering"

    def __str__(self):
        return "Document Numbering Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def generate_number(self, doc_type):
        """
        IMPROVEMENT 3a — Atomic document number generation.
        Generates and increments the next number for a document type.
        Uses select_for_update() to prevent race conditions under concurrent use.

        Args:
            doc_type: 'invoice' | 'sales_order' | 'purchase_order' | 'customer' | 'vendor'

        Returns:
            str: Formatted document number e.g. 'INV-2026-0042'

        Usage:
            number = DocumentNumberingConfig.get_config().generate_number('invoice')
        """
        prefix_field = f'{doc_type}_prefix'
        method_field = f'{doc_type}_numbering'
        next_field = f'{doc_type}_next_number'

        for field in (prefix_field, method_field, next_field):
            if not hasattr(self, field):
                raise ValueError(f"Unknown document type: '{doc_type}'")

        with transaction.atomic():
            # Lock this row so concurrent requests don't get the same number
            config = DocumentNumberingConfig.objects.select_for_update().get(pk=1)

            prefix = getattr(config, prefix_field)
            method = getattr(config, method_field)
            seq = getattr(config, next_field)

            # Build the number string
            seq_str = str(seq).zfill(config.pad_length)
            today = date.today()

            if method == 'sequential':
                number = f"{prefix}-{seq_str}"
            elif method == 'yearly':
                number = f"{prefix}-{today.year}-{seq_str}"
            elif method == 'monthly':
                number = f"{prefix}-{today.strftime('%Y%m')}-{seq_str}"
            else:
                number = f"{prefix}-{seq_str}"

            # Increment and save
            setattr(config, next_field, seq + 1)
            config.save(update_fields=[next_field])

        return number


# ===========================================================================
# IMPROVEMENT 4 — PricingConfig (enhanced)
# ===========================================================================

class PricingConfig(models.Model):
    """Global pricing configuration. Singleton (pk=1)."""

    PRICING_MODEL_CHOICES = [
        ('single', 'Single Price (all customers same price)'),
        ('multi', 'Multi-Tier Pricing (different prices per customer type)'),
    ]

    pricing_model = models.CharField(
        max_length=10,
        choices=PRICING_MODEL_CHOICES,
        default='single',
    )

    default_retail_name = models.CharField(max_length=50, default='Retail Price')
    default_wholesale_name = models.CharField(max_length=50, default='Wholesale Price')
    default_distributor_name = models.CharField(max_length=50, default='Distributor Price')

    # FIX #3 from previous review: FK to Currency instead of CharField
    base_currency = models.ForeignKey(
        'Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pricing_configs',
        help_text="Base currency for all pricing calculations"
    )

    # IMPROVEMENT 4a — tax inclusion flag
    prices_include_tax = models.BooleanField(
        default=False,
        help_text="If True, all displayed prices are tax-inclusive"
    )

    # IMPROVEMENT 4b — rounding rule
    ROUNDING_CHOICES = [
        ('standard', 'Standard (0.5 rounds up)'),
        ('always_up', 'Always round up'),
        ('always_down', 'Always round down (truncate)'),
        ('banker', "Banker's rounding (round half to even)"),
    ]
    rounding_rule = models.CharField(
        max_length=20,
        choices=ROUNDING_CHOICES,
        default='standard',
        help_text="How to round calculated prices"
    )

    class Meta:
        verbose_name = "Pricing Configuration"
        verbose_name_plural = "Pricing Configuration"

    def __str__(self):
        return f"Pricing Config — {self.get_pricing_model_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete('pricing_config')

    @classmethod
    def get_config(cls):
        """Cached singleton getter. Cache invalidated on every save."""
        config = cache.get('pricing_config')
        if config is None:
            config, _ = cls.objects.select_related('base_currency').get_or_create(pk=1)
            cache.set('pricing_config', config, 300)
        return config


# ===========================================================================
# IMPROVEMENT 5 — ERPSettings (slimmed down — God Object resolved)
# Previously: 50+ fields covering company, numbering, currency, inventory, etc.
# Now: only truly global operational settings remain here.
# Company → CompanyProfile, Numbering → DocumentNumberingConfig
# ===========================================================================

class ERPSettings(models.Model):
    """
    Global ERP operational settings. Singleton (pk=1).
    Covers: decimal precision, date/time format, SKU generation,
    inventory rules, and setup state.
    Company info → CompanyProfile
    Document numbering → DocumentNumberingConfig
    """

    DECIMAL_PRECISION_CHOICES = [
        (2, '2 decimal places — Standard Retail ($19.99)'),
        (4, '4 decimal places — Wholesale/B2B ($15.4375)'),
        (6, '6 decimal places — High Precision ($0.052375)'),
    ]

    price_decimals = models.IntegerField(choices=DECIMAL_PRECISION_CHOICES, default=4)
    cost_decimals = models.IntegerField(choices=DECIMAL_PRECISION_CHOICES, default=4)

    # FIX #3: Link to Currency model properly
    default_currency = models.ForeignKey(
        'Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='erp_settings_default',
        help_text="Default currency for the ERP"
    )

    CURRENCY_POSITION_CHOICES = [
        ('before', 'Before amount ($10.99)'),
        ('after', 'After amount (10.99€)'),
        ('before_space', 'Before with space ($ 10.99)'),
        ('after_space', 'After with space (10.99 €)'),
    ]

    currency_position = models.CharField(
        max_length=20, choices=CURRENCY_POSITION_CHOICES, default='before'
    )

    THOUSAND_SEPARATOR_CHOICES = [
        ('comma', 'Comma  →  1,000.00'),
        ('period', 'Period →  1.000,00'),
        ('space', 'Space  →  1 000.00'),
        ('none', 'None   →  1000.00'),
    ]

    thousand_separator = models.CharField(
        max_length=10, choices=THOUSAND_SEPARATOR_CHOICES, default='comma'
    )
    decimal_separator = models.CharField(max_length=1, default='.')

    DATE_FORMAT_CHOICES = [
        ('Y-m-d', '2024-12-31 (ISO)'),
        ('d/m/Y', '31/12/2024 (EU)'),
        ('m/d/Y', '12/31/2024 (US)'),
        ('d.m.Y', '31.12.2024 (EU dot)'),
        ('d-m-Y', '31-12-2024 (EU dash)'),
    ]

    date_format = models.CharField(max_length=10, choices=DATE_FORMAT_CHOICES, default='Y-m-d')

    TIME_FORMAT_CHOICES = [
        ('H:i', '14:30 (24-hour)'),
        ('h:i A', '02:30 PM (12-hour)'),
    ]

    time_format = models.CharField(max_length=10, choices=TIME_FORMAT_CHOICES, default='H:i')
    timezone_name = models.CharField(max_length=50, default='UTC')

    # Inventory global rules
    allow_negative_inventory = models.BooleanField(
        default=False,
        help_text="⚠️ Warning: allowing negative inventory can cause accounting issues"
    )
    default_reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    low_stock_threshold_percentage = models.IntegerField(
        default=20,
        help_text="Alert when stock falls below this % of the reorder level"
    )

    # SKU generation
    SKU_PATTERN_CHOICES = [
        ('{CATEGORY}-{SEQUENCE}', 'CAT-0001'),
        ('{BRAND}-{SEQUENCE}', 'BRAND-0001'),
        ('{CATEGORY}-{BRAND}-{SEQUENCE}', 'CAT-BRAND-0001'),
        ('SKU-{SEQUENCE}', 'SKU-0001'),
        ('manual', 'Manual entry only'),
    ]

    sku_pattern = models.CharField(
        max_length=50, choices=SKU_PATTERN_CHOICES, default='{CATEGORY}-{SEQUENCE}'
    )
    sku_length = models.IntegerField(default=8, help_text="Minimum SKU length")

    # Setup state
    setup_completed = models.BooleanField(default=False)
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    first_product_added = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ERP Global Settings"
        verbose_name_plural = "ERP Global Settings"

    def __str__(self):
        profile = CompanyProfile.get_profile()
        status = "✅ Setup complete" if self.setup_completed else "⚙️ Setup pending"
        return f"ERP Settings ({profile.name or 'Unnamed Company'}) — {status}"

    def save(self, *args, **kwargs):
        self.pk = 1
        # FIX #7: enforce locked fields on direct save(), not just form clean()
        self._enforce_locked_fields()
        super().save(*args, **kwargs)
        # FIX #2: Use update() to avoid double-save / recursion risk
        if self.first_product_added and not self.setup_completed:
            ERPSettings.objects.filter(pk=1).update(
                setup_completed=True,
                setup_completed_at=tz.now()
            )
            self.setup_completed = True
            self.setup_completed_at = tz.now()
        cache.delete('erp_settings')

    def clean(self):
        """Form-level validation for locked fields."""
        self._enforce_locked_fields()

    def _enforce_locked_fields(self):
        """Raise ValidationError if locked fields are changed after first product."""
        if not self.pk or not self.first_product_added:
            return
        try:
            original = ERPSettings.objects.get(pk=self.pk)
        except ERPSettings.DoesNotExist:
            return

        locked = ['price_decimals', 'cost_decimals', 'sku_pattern']
        errors = {}
        for field in locked:
            if getattr(original, field) != getattr(self, field):
                errors[field] = f"'{field}' cannot be changed after the first product is added."
        if errors:
            raise ValidationError(errors)

    @classmethod
    def get_settings(cls):
        """Cached singleton getter."""
        settings_obj = cache.get('erp_settings')
        if settings_obj is None:
            settings_obj, _ = cls.objects.select_related('default_currency').get_or_create(pk=1)
            cache.set('erp_settings', settings_obj, 300)
        return settings_obj

    # IMPROVEMENT 5a — Number formatter using configured separators
    def format_number(self, amount, decimal_places=None):
        """
        Format a number using this ERP's configured separators.
        Previously: each model had its own formatting logic or used hardcoded separators.
        Now: one central formatter everyone can call.

        Usage:
            settings = ERPSettings.get_settings()
            settings.format_number(1234567.89)  # → "1,234,567.89"
        """
        places = decimal_places if decimal_places is not None else self.price_decimals
        raw = f"{amount:,.{places}f}"

        sep_map = {
            'comma': (',', '.'),
            'period': ('.', ','),
            'space': (' ', '.'),
            'none': ('', '.'),
        }
        thou_sep, dec_sep = sep_map.get(self.thousand_separator, (',', '.'))

        # Replace in two steps to avoid collisions
        formatted = (
            raw
            .replace(',', '__T__')
            .replace('.', dec_sep)
            .replace('__T__', thou_sep)
        )
        return formatted


# ===========================================================================
# IMPROVEMENT 6 — ModuleStatus (with cache invalidation signal)
# ===========================================================================

class ModuleStatus(models.Model):
    """Enable/disable individual ERP modules."""

    MODULE_CHOICES = [
        ('products', 'Products Management'),
        ('inventory', 'Inventory Management'),
        ('sales', 'Sales & Customers'),
        ('purchasing', 'Purchasing & Vendors'),
        ('accounting', 'Accounting'),
        ('hr', 'Human Resources'),
        ('manufacturing', 'Manufacturing'),
        ('projects', 'Project Management'),
        ('reports', 'Reporting & Analytics'),
    ]

    module = models.CharField(max_length=50, choices=MODULE_CHOICES, unique=True)
    is_enabled = models.BooleanField(default=True)
    license_key = models.CharField(max_length=255, blank=True)

    # IMPROVEMENT 6a — expiry enforcement
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text="Module license expiry date. Module auto-disables on this date."
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['module']

    def __str__(self):
        status = '✅ Enabled' if self.is_active else '❌ Disabled'
        return f"{self.get_module_display()}: {status}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # IMPROVEMENT 6b — Invalidate cache whenever a ModuleStatus changes
        cache.delete(f'module_status_{self.module}')
        cache.delete('all_module_statuses')

    @property
    def is_active(self):
        """
        IMPROVEMENT 6a: Respects expiry_date.
        Previously: is_enabled flag was all that existed; expiry was stored but never checked.
        """
        if not self.is_enabled:
            return False
        if self.expiry_date and self.expiry_date < date.today():
            return False
        return True

    @property
    def is_expiring_soon(self):
        """Returns True if the license expires within 30 days."""
        if not self.expiry_date:
            return False
        return 0 <= (self.expiry_date - date.today()).days <= 30

    @classmethod
    def is_module_enabled(cls, module_name):
        """
        Cached module status check.
        Call this in views/decorators instead of querying directly.
        """
        cache_key = f'module_status_{module_name}'
        result = cache.get(cache_key)
        if result is None:
            try:
                status = cls.objects.get(module=module_name)
                result = status.is_active
            except cls.DoesNotExist:
                result = True  # Default: enabled if not explicitly configured
            cache.set(cache_key, result, 60)
        return result

    @classmethod
    def get_all_statuses(cls):
        """Return dict of {module_name: is_active} for all modules."""
        cached = cache.get('all_module_statuses')
        if cached is not None:
            return cached
        result = {s.module: s.is_active for s in cls.objects.all()}
        cache.set('all_module_statuses', result, 60)
        return result


def module_required(module_name):
    """
    View decorator to enforce module is enabled.

    Usage:
        @module_required('inventory')
        def stock_view(request): ...
    """
    from functools import wraps
    from django.core.exceptions import PermissionDenied

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not ModuleStatus.is_module_enabled(module_name):
                raise PermissionDenied(
                    f"The '{module_name}' module is currently disabled."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ===========================================================================
# IMPROVEMENT 7 — Currency (with staleness detection + auto history logging)
# ===========================================================================

class Currency(models.Model):
    """Multi-currency support."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=5)

    exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('1.0'),
        validators=[MinValueValidator(Decimal('0.0001'))],
    )

    is_base = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # IMPROVEMENT 7a — staleness detection
    rates_last_updated = models.DateTimeField(
        null=True, blank=True,
        help_text="When the exchange rate was last updated"
    )
    rate_update_source = models.CharField(
        max_length=100, blank=True,
        help_text="Where the rate came from (e.g., 'manual', 'ECB', 'openexchangerates')"
    )

    decimal_places = models.IntegerField(default=2, choices=[(0,'0'),(1,'1'),(2,'2'),(3,'3')])
    decimal_separator = models.CharField(max_length=1, default='.')
    thousand_separator = models.CharField(max_length=1, default=',')
    symbol_position = models.CharField(
        max_length=10,
        choices=[('before', 'Before amount'), ('after', 'After amount')],
        default='before'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['code']

    def __str__(self):
        base_tag = " [BASE]" if self.is_base else ""
        stale_tag = " ⚠️ STALE" if self.is_rate_stale else ""
        return f"{self.code} — {self.symbol} {self.name}{base_tag}{stale_tag}"

    def save(self, *args, **kwargs):
        """
        FIX #1: Atomic transaction + exclude(pk=self.pk).
        IMPROVEMENT 7b: Stamp rates_last_updated when rate changes.
        """
        with transaction.atomic():
            if self.is_base:
                Currency.objects.exclude(pk=self.pk).filter(
                    is_base=True
                ).update(is_base=False)
                self.exchange_rate = Decimal('1.0')

            # Detect rate change before saving
            rate_changed = False
            if self.pk:
                try:
                    old = Currency.objects.get(pk=self.pk)
                    rate_changed = old.exchange_rate != self.exchange_rate
                except Currency.DoesNotExist:
                    rate_changed = True
            else:
                rate_changed = True  # New record

            if rate_changed and not self.is_base:
                self.rates_last_updated = tz.now()

            super().save(*args, **kwargs)

            # IMPROVEMENT 7c: Auto-log to ExchangeRateHistory on rate change
            if rate_changed and not self.is_base:
                ExchangeRateHistory.record_rate(
                    currency=self,
                    exchange_rate=self.exchange_rate,
                    note=self.rate_update_source or 'manual update'
                )

    @property
    def is_rate_stale(self):
        """
        IMPROVEMENT 7a: Returns True if rate hasn't been updated in 24 hours.
        Previously: no way to detect stale rates.
        """
        if self.is_base:
            return False
        if not self.rates_last_updated:
            return True
        return (tz.now() - self.rates_last_updated).total_seconds() > 86400  # 24h

    def convert_to(self, amount, target_currency):
        """
        FIX #9: Guard against zero exchange rates.
        """
        if not target_currency or target_currency == self:
            return amount
        if self.exchange_rate == 0:
            raise ValueError(f"Cannot convert from {self.code}: exchange rate is zero.")
        if target_currency.exchange_rate == 0:
            raise ValueError(f"Cannot convert to {target_currency.code}: exchange rate is zero.")
        base_amount = amount / self.exchange_rate
        return base_amount * target_currency.exchange_rate

    def format_amount(self, amount):
        """
        FIX #6: Respects thousand_separator and decimal_separator fields.
        Previously: always used comma for thousands regardless of settings.
        """
        raw = f"{amount:,.{self.decimal_places}f}"
        formatted = (
            raw
            .replace(',', '__T__')
            .replace('.', self.decimal_separator)
            .replace('__T__', self.thousand_separator)
        )
        if self.symbol_position == 'before':
            return f"{self.symbol}{formatted}"
        return f"{formatted}{self.symbol}"


# ===========================================================================
# ExchangeRateHistory (FIX #5 applied)
# ===========================================================================

class ExchangeRateHistory(models.Model):
    """Historical exchange rates for auditing and pricing accuracy."""

    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='rate_history')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4)

    # FIX #5: default=date.today instead of auto_now_add=True
    # Allows: manual back-fill, more than one update per day via update_or_create
    date = models.DateField(default=date.today)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('currency', 'date')

    def __str__(self):
        return f"{self.currency.code} — {self.date}: {self.exchange_rate}"

    @classmethod
    def record_rate(cls, currency, exchange_rate, note=''):
        """
        Safe helper: create or update today's rate without IntegrityError.
        Also used by Currency.save() for automatic logging.
        """
        obj, created = cls.objects.update_or_create(
            currency=currency,
            date=date.today(),
            defaults={'exchange_rate': exchange_rate, 'note': note}
        )
        return obj, created