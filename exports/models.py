from django.conf import settings
from django.db import models


FORMAT_CHOICES = [
    ('excel', 'Excel (.xlsx)'),
    ('csv', 'CSV (.csv)'),
    ('pdf', 'PDF (.pdf)'),
    ('json', 'JSON (.json)'),
    ('ods', 'ODS (.ods)'),
    ('zip', 'ZIP Archive'),
    ('google_sheets', 'Google Sheets (coming soon)'),
    ('none', 'No Export'),
]

MODULE_CHOICES = [
    ('products.product', 'Products - Product'),
    ('products.unit', 'Products - Unit'),
    ('products.brand', 'Products - Brand'),
    ('products.productcategory', 'Products - Category'),
    ('products.pricelist', 'Products - Price List'),
    ('products.productattribute', 'Products - Product Attribute'),
    ('products.productattributevalue', 'Products - Attribute Value'),
    ('products.productvariant', 'Products - Product Variant'),
    ('products.productpricehistory', 'Products - Price History'),
    ('inventory.stock', 'Inventory - Stock'),
    ('inventory.stockbatch', 'Inventory - Stock Batch'),
    ('inventory.stockmovement', 'Inventory - Stock Movement'),
    ('inventory.warehouse', 'Inventory - Warehouse'),
    ('inventory.warehousesection', 'Inventory - Warehouse Section'),
    ('purchasing.purchaseorder', 'Purchasing - Purchase Order'),
    ('purchasing.vendor', 'Purchasing - Vendor'),
    ('purchasing.purchasereceipt', 'Purchasing - Purchase Receipt'),
    ('sales.customer', 'Sales - Customer'),
    ('sales.salesorder', 'Sales - Sales Order'),
    ('accounting.invoice', 'Accounting - Invoice'),
    ('accounting.bill', 'Accounting - Bill'),
    ('accounting.payment', 'Accounting - Payment'),
    ('accounting.journalentry', 'Accounting - Journal Entry'),
]

DATE_FORMAT_CHOICES = [
    ('%Y-%m-%d', 'YYYY-MM-DD (2025-01-31)'),
    ('%d/%m/%Y', 'DD/MM/YYYY (31/01/2025)'),
    ('%m/%d/%Y', 'MM/DD/YYYY (01/31/2025)'),
    ('%d-%m-%Y', 'DD-MM-YYYY (31-01-2025)'),
    ('%d %b %Y', 'DD Mon YYYY (31 Jan 2025)'),
]


class ExportConfig(models.Model):
    """
    One record per module-model combination.
    Superusers configure which formats are enabled and the default options per model.
    Auto-created with sensible defaults on first access via get_for_model().
    """
    module_key = models.CharField(
        max_length=100,
        choices=MODULE_CHOICES,
        unique=True,
        help_text="The model this config applies to (app_label.model_name)",
    )
    enabled_formats = models.JSONField(
        default=list,
        help_text='Enabled format strings, e.g. ["excel", "csv", "json"]',
    )
    default_format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default='excel',
    )
    include_headers_default = models.BooleanField(default=True)
    include_footer_default = models.BooleanField(default=False)
    compress_zip_default = models.BooleanField(default=False)
    date_format_default = models.CharField(
        max_length=30,
        default='%Y-%m-%d',
        choices=DATE_FORMAT_CHOICES,
        help_text="Python strftime format for dates in exports",
    )
    max_rows = models.PositiveIntegerField(
        default=10000,
        help_text="Maximum rows per export. 0 = unlimited.",
    )
    require_staff = models.BooleanField(
        default=True,
        help_text="If True, only staff users can export from this module",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If False, no export actions are shown for this module",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Export Configuration"
        verbose_name_plural = "Export Configurations"
        ordering = ['module_key']

    def __str__(self):
        return f"Export Config: {self.get_module_key_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._clear_cache()

    def _clear_cache(self):
        from django.core.cache import cache
        parts = self.module_key.split('.')
        if len(parts) == 2:
            cache.delete(f'export_config_{parts[0]}_{parts[1]}')

    @classmethod
    def get_for_model(cls, app_label: str, model_name: str) -> 'ExportConfig':
        """
        Fetch (or auto-create) the ExportConfig for the given model.
        Results are cached for 5 minutes.
        """
        from django.core.cache import cache
        cache_key = f'export_config_{app_label}_{model_name}'
        config = cache.get(cache_key)
        if config is None:
            config, _ = cls.objects.get_or_create(
                module_key=f'{app_label}.{model_name}',
                defaults={
                    'enabled_formats': ['excel', 'csv', 'json'],
                    'default_format': 'excel',
                }
            )
            cache.set(cache_key, config, 300)
        return config


class UserExportPreference(models.Model):
    """
    Per-user overrides for export options. Falls back to ExportConfig defaults
    when no record exists for (user, module_key).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='export_preferences',
    )
    module_key = models.CharField(
        max_length=100,
        choices=MODULE_CHOICES,
    )
    preferred_format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default='excel',
    )
    include_headers = models.BooleanField(default=True)
    include_footer = models.BooleanField(default=False)
    compress_zip = models.BooleanField(default=False)
    date_format = models.CharField(
        max_length=30,
        default='%Y-%m-%d',
        choices=DATE_FORMAT_CHOICES,
    )

    class Meta:
        unique_together = [('user', 'module_key')]
        verbose_name = "User Export Preference"
        verbose_name_plural = "User Export Preferences"
        ordering = ['user', 'module_key']

    def __str__(self):
        return f"{self.user.username} / {self.module_key} → {self.preferred_format}"


class UserColumnPreference(models.Model):
    """
    Per-user, per-model column visibility and ordering for admin list views.
    Persists across sessions so users always see their preferred columns.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='column_preferences',
    )
    model_key = models.CharField(
        max_length=100,
        help_text="App + model label, e.g. 'products.unit'",
    )
    columns = models.JSONField(
        default=list,
        help_text="Ordered list of visible column field names",
    )

    class Meta:
        unique_together = [('user', 'model_key')]
        verbose_name = "User Column Preference"
        verbose_name_plural = "User Column Preferences"

    def __str__(self):
        return f"{self.user.username} / {self.model_key} columns"


class ExportLog(models.Model):
    """
    Immutable audit record for every export action. Never updated after creation.
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial (row limit hit)'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='export_logs',
    )
    module_key = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100, blank=True)
    export_format = models.CharField(max_length=20)

    # Options used for this export
    include_headers = models.BooleanField(default=True)
    include_footer = models.BooleanField(default=False)
    compressed = models.BooleanField(default=False)
    date_format = models.CharField(max_length=30, default='%Y-%m-%d')

    # Results
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    record_count = models.PositiveIntegerField(default=0)
    file_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Export Log"
        verbose_name_plural = "Export Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['module_key', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        username = self.user.username if self.user else 'Anonymous'
        ts = self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '?'
        return f"{username} exported {self.module_key} as {self.export_format} at {ts}"

    @property
    def file_size_kb(self):
        if self.file_size_bytes:
            return round(self.file_size_bytes / 1024, 1)
        return None
