"""
config_settings/signals.py
============================
Handles two responsibilities:
  1. Cache invalidation  — clears cached singleton values whenever settings change
  2. Change logging      — writes SettingsChangeLog entries for important field changes

Registered in config_settings/apps.py via:
    def ready(self):
        import config_settings.signals  # noqa
"""

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone

from .models import (
    Currency,
    ERPSettings,
    PricingConfig,
    ModuleStatus,
    CompanyProfile,
    DocumentNumberingConfig,
    ExchangeRateHistory,
    SettingsChangeLog,
)


# ===========================================================================
# SECTION 1 — CACHE INVALIDATION
# Every singleton model has a cache key set in get_config() / get_settings().
# These signals make sure the cache is always cleared on save/delete.
# ===========================================================================

# ---------------------------------------------------------------------------
# ERPSettings
# ---------------------------------------------------------------------------

@receiver(post_save, sender=ERPSettings)
def invalidate_erp_settings_cache(sender, instance, **kwargs):
    """Clear cached ERPSettings singleton on every save."""
    cache.delete('erp_settings')


# ---------------------------------------------------------------------------
# CompanyProfile
# ---------------------------------------------------------------------------

@receiver(post_save, sender=CompanyProfile)
def invalidate_company_profile_cache(sender, instance, **kwargs):
    """Clear cached CompanyProfile singleton on every save."""
    cache.delete('company_profile')


# ---------------------------------------------------------------------------
# PricingConfig
# ---------------------------------------------------------------------------

@receiver(post_save, sender=PricingConfig)
def invalidate_pricing_config_cache(sender, instance, **kwargs):
    """Clear cached PricingConfig singleton on every save."""
    cache.delete('pricing_config')


# ---------------------------------------------------------------------------
# DocumentNumberingConfig
# ---------------------------------------------------------------------------

@receiver(post_save, sender=DocumentNumberingConfig)
def invalidate_numbering_config_cache(sender, instance, **kwargs):
    """Clear cached DocumentNumberingConfig on every save."""
    cache.delete('doc_numbering_config')


# ---------------------------------------------------------------------------
# ModuleStatus — per-module AND full list cache
# ---------------------------------------------------------------------------

@receiver(post_save, sender=ModuleStatus)
def invalidate_module_status_cache_on_save(sender, instance, **kwargs):
    """
    Clear both the per-module cache key and the full statuses dict.
    Both are set in ModuleStatus.is_module_enabled() and get_all_statuses().
    """
    cache.delete(f'module_status_{instance.module}')
    cache.delete('all_module_statuses')


@receiver(post_delete, sender=ModuleStatus)
def invalidate_module_status_cache_on_delete(sender, instance, **kwargs):
    """Also clear cache when a ModuleStatus record is deleted."""
    cache.delete(f'module_status_{instance.module}')
    cache.delete('all_module_statuses')


# ---------------------------------------------------------------------------
# Currency — clear any currency-specific caches
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Currency)
def invalidate_currency_cache(sender, instance, **kwargs):
    """
    Clear currency-related cache keys.
    Products and sales modules may cache currency lookups.
    """
    cache.delete(f'currency_{instance.code}')
    cache.delete(f'currency_{instance.pk}')
    cache.delete('base_currency')
    cache.delete('active_currencies')


@receiver(post_delete, sender=Currency)
def invalidate_currency_cache_on_delete(sender, instance, **kwargs):
    """Also clear cache when a currency is deleted."""
    cache.delete(f'currency_{instance.code}')
    cache.delete(f'currency_{instance.pk}')
    cache.delete('base_currency')
    cache.delete('active_currencies')


# ===========================================================================
# SECTION 2 — CHANGE LOGGING
# Tracks before/after values for important fields across all settings models.
# Uses pre_save to capture old values, post_save to write the log entries.
#
# Pattern used throughout:
#   pre_save  → compare old vs new, store diffs on instance.__dict__
#   post_save → read diffs from instance.__dict__, write SettingsChangeLog rows
#
# This approach is safe because instance.__dict__ is local to this save cycle.
# ===========================================================================

# ---------------------------------------------------------------------------
# Fields to track per model
# ---------------------------------------------------------------------------

ERP_SETTINGS_TRACKED_FIELDS = [
    'price_decimals',
    'cost_decimals',
    'default_currency_id',      # FK — track the ID change
    'currency_position',
    'thousand_separator',
    'decimal_separator',
    'allow_negative_inventory',
    'sku_pattern',
    'sku_length',
    'date_format',
    'time_format',
    'timezone_name',
    'low_stock_threshold_percentage',
    'default_reorder_level',
]

PRICING_CONFIG_TRACKED_FIELDS = [
    'pricing_model',
    'base_currency_id',         # FK
    'prices_include_tax',
    'rounding_rule',
    'default_retail_name',
    'default_wholesale_name',
    'default_distributor_name',
]

COMPANY_PROFILE_TRACKED_FIELDS = [
    'name',
    'email',
    'phone',
    'tax_id',
    'fiscal_year_start',
    'fiscal_year_end',
]

MODULE_STATUS_TRACKED_FIELDS = [
    'is_enabled',
    'expiry_date',
    'license_key',
]

CURRENCY_TRACKED_FIELDS = [
    'exchange_rate',
    'is_base',
    'is_active',
    'decimal_places',
    'decimal_separator',
    'thousand_separator',
    'symbol_position',
]


# ---------------------------------------------------------------------------
# Generic helper: diff two model instances and store changed fields
# ---------------------------------------------------------------------------

def _store_diffs(instance, old_instance, tracked_fields):
    """
    Compare old vs new values for tracked_fields.
    Stores diffs as _changed_<fieldname> = (old_val, new_val) on instance.__dict__.
    These are read in the post_save signal to write log entries.
    """
    for field in tracked_fields:
        old_val = getattr(old_instance, field, None)
        new_val = getattr(instance, field, None)
        if str(old_val) != str(new_val):   # str() handles Decimal, date comparisons
            instance.__dict__[f'_changed_{field}'] = (old_val, new_val)


def _write_change_logs(instance, setting_type, tracked_fields, label_overrides=None):
    """
    Read _changed_<field> keys stored by _store_diffs() and write SettingsChangeLog rows.

    Args:
        instance:        the saved model instance
        setting_type:    string key for SettingsChangeLog.setting_type
        tracked_fields:  list of field names to check
        label_overrides: optional dict mapping field_name → human readable label
    """
    label_overrides = label_overrides or {}
    for field in tracked_fields:
        key = f'_changed_{field}'
        if key in instance.__dict__:
            old_val, new_val = instance.__dict__.pop(key)
            display_field = label_overrides.get(field, field)
            SettingsChangeLog.log_change(
                setting_type=setting_type,
                setting_id=instance.pk,
                field_name=display_field,
                old_value=old_val,
                new_value=new_val,
            )


# ---------------------------------------------------------------------------
# ERPSettings change tracking
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=ERPSettings)
def track_erp_settings_changes(sender, instance, **kwargs):
    """Capture ERPSettings field changes before save."""
    if not instance.pk:
        return  # New record — nothing to diff
    try:
        old = ERPSettings.objects.get(pk=instance.pk)
    except ERPSettings.DoesNotExist:
        return
    _store_diffs(instance, old, ERP_SETTINGS_TRACKED_FIELDS)


@receiver(post_save, sender=ERPSettings)
def log_erp_settings_changes(sender, instance, created, **kwargs):
    """Write SettingsChangeLog entries for ERPSettings field changes."""
    if created:
        # Log the initial creation as a single entry
        SettingsChangeLog.log_change(
            setting_type='erp_settings',
            setting_id=instance.pk,
            field_name='record',
            old_value=None,
            new_value='Created',
        )
        return

    _write_change_logs(
        instance,
        setting_type='erp_settings',
        tracked_fields=ERP_SETTINGS_TRACKED_FIELDS,
        label_overrides={
            'default_currency_id': 'default_currency',
        }
    )


# ---------------------------------------------------------------------------
# PricingConfig change tracking
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=PricingConfig)
def track_pricing_config_changes(sender, instance, **kwargs):
    """Capture PricingConfig field changes before save."""
    if not instance.pk:
        return
    try:
        old = PricingConfig.objects.get(pk=instance.pk)
    except PricingConfig.DoesNotExist:
        return
    _store_diffs(instance, old, PRICING_CONFIG_TRACKED_FIELDS)


@receiver(post_save, sender=PricingConfig)
def log_pricing_config_changes(sender, instance, created, **kwargs):
    """Write SettingsChangeLog entries for PricingConfig field changes."""
    if created:
        SettingsChangeLog.log_change(
            setting_type='pricing_config',
            setting_id=instance.pk,
            field_name='record',
            old_value=None,
            new_value='Created',
        )
        return

    _write_change_logs(
        instance,
        setting_type='pricing_config',
        tracked_fields=PRICING_CONFIG_TRACKED_FIELDS,
        label_overrides={
            'base_currency_id': 'base_currency',
        }
    )


# ---------------------------------------------------------------------------
# CompanyProfile change tracking
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=CompanyProfile)
def track_company_profile_changes(sender, instance, **kwargs):
    """Capture CompanyProfile field changes before save."""
    if not instance.pk:
        return
    try:
        old = CompanyProfile.objects.get(pk=instance.pk)
    except CompanyProfile.DoesNotExist:
        return
    _store_diffs(instance, old, COMPANY_PROFILE_TRACKED_FIELDS)


@receiver(post_save, sender=CompanyProfile)
def log_company_profile_changes(sender, instance, created, **kwargs):
    """Write SettingsChangeLog entries for CompanyProfile field changes."""
    if created:
        SettingsChangeLog.log_change(
            setting_type='company_profile',
            setting_id=instance.pk,
            field_name='record',
            old_value=None,
            new_value=f"Created: {instance.name or 'Unnamed'}",
        )
        return

    _write_change_logs(
        instance,
        setting_type='company_profile',
        tracked_fields=COMPANY_PROFILE_TRACKED_FIELDS,
    )


# ---------------------------------------------------------------------------
# ModuleStatus change tracking
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=ModuleStatus)
def track_module_status_changes(sender, instance, **kwargs):
    """Capture ModuleStatus field changes before save."""
    if not instance.pk:
        return
    try:
        old = ModuleStatus.objects.get(pk=instance.pk)
    except ModuleStatus.DoesNotExist:
        return
    _store_diffs(instance, old, MODULE_STATUS_TRACKED_FIELDS)


@receiver(post_save, sender=ModuleStatus)
def log_module_status_changes(sender, instance, created, **kwargs):
    """Write SettingsChangeLog entries for ModuleStatus field changes."""
    if created:
        SettingsChangeLog.log_change(
            setting_type='module_status',
            setting_id=instance.pk,
            field_name='module',
            old_value=None,
            new_value=f"{instance.module} — {'Enabled' if instance.is_enabled else 'Disabled'}",
        )
        return

    _write_change_logs(
        instance,
        setting_type='module_status',
        tracked_fields=MODULE_STATUS_TRACKED_FIELDS,
        label_overrides={
            'is_enabled': f'module:{instance.module}:is_enabled',
            'expiry_date': f'module:{instance.module}:expiry_date',
        }
    )


# ---------------------------------------------------------------------------
# Currency change tracking
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=Currency)
def track_currency_changes(sender, instance, **kwargs):
    """
    Capture Currency field changes before save.
    Exchange rate changes are already auto-logged to ExchangeRateHistory
    in Currency.save() — we only log the other fields here to SettingsChangeLog.
    """
    if not instance.pk:
        return
    try:
        old = Currency.objects.get(pk=instance.pk)
    except Currency.DoesNotExist:
        return

    # Exclude exchange_rate — it's tracked in ExchangeRateHistory already
    fields_to_track = [f for f in CURRENCY_TRACKED_FIELDS if f != 'exchange_rate']
    _store_diffs(instance, old, fields_to_track)

    # For exchange_rate specifically, only store diff for SettingsChangeLog
    # so we have a record alongside the ExchangeRateHistory entry
    old_rate = old.exchange_rate
    new_rate = instance.exchange_rate
    if old_rate != new_rate:
        instance.__dict__['_changed_exchange_rate'] = (old_rate, new_rate)


@receiver(post_save, sender=Currency)
def log_currency_changes(sender, instance, created, **kwargs):
    """Write SettingsChangeLog entries for Currency field changes."""
    if created:
        SettingsChangeLog.log_change(
            setting_type='currency',
            setting_id=instance.pk,
            field_name='record',
            old_value=None,
            new_value=f"Created: {instance.code} ({instance.name})",
        )
        return

    # Log all tracked field changes
    fields_to_log = [f for f in CURRENCY_TRACKED_FIELDS if f != 'exchange_rate']
    _write_change_logs(
        instance,
        setting_type='currency',
        tracked_fields=fields_to_log,
        label_overrides={
            'is_base': f'{instance.code}:is_base',
            'is_active': f'{instance.code}:is_active',
        }
    )

    # Log exchange_rate change separately with the currency code in the label
    rate_change_key = '_changed_exchange_rate'
    if rate_change_key in instance.__dict__:
        old_val, new_val = instance.__dict__.pop(rate_change_key)
        SettingsChangeLog.log_change(
            setting_type='currency',
            setting_id=instance.pk,
            field_name=f'{instance.code}:exchange_rate',
            old_value=old_val,
            new_value=new_val,
        )


# ===========================================================================
# SECTION 3 — ExchangeRateHistory auto-snapshot
# When a Currency exchange rate changes, auto-record a daily snapshot.
# This is a safety net — Currency.save() already calls record_rate(),
# but this signal catches any bulk update() calls that bypass save().
# NOTE: Django signals do NOT fire for queryset.update() calls.
# If you use bulk updates for rates, call ExchangeRateHistory.record_rate()
# explicitly in that code path.
# ===========================================================================

@receiver(post_save, sender=Currency)
def auto_snapshot_exchange_rate(sender, instance, created, **kwargs):
    """
    Auto-snapshot exchange rate to ExchangeRateHistory after every currency save.
    Currency.save() already does this for normal saves, but this acts as a
    safety net for any code path that calls super().save() directly.

    Uses update_or_create so duplicate entries for the same date are safe.
    """
    if instance.is_base:
        return  # Base currency rate is always 1.0 — no need to snapshot

    # Check if this save actually changed the rate to avoid unnecessary writes
    rate_changed = '_changed_exchange_rate' in instance.__dict__ or created
    if rate_changed:
        ExchangeRateHistory.record_rate(
            currency=instance,
            exchange_rate=instance.exchange_rate,
            note=instance.rate_update_source or 'auto-snapshot on save',
        )