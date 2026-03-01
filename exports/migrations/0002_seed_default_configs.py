from django.db import migrations


DEFAULT_CONFIGS = [
    # Products
    {'module_key': 'products.product',             'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'products.unit',                'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.brand',               'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.productcategory',     'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.pricelist',           'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.productattribute',    'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.productattributevalue', 'enabled_formats': ['excel', 'csv'],       'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.productvariant',      'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'products.productpricehistory', 'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    # Inventory
    {'module_key': 'inventory.stock',              'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'inventory.stockbatch',         'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'inventory.stockmovement',      'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'inventory.warehouse',          'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 1000},
    {'module_key': 'inventory.warehousesection',   'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 5000},
    # Purchasing
    {'module_key': 'purchasing.purchaseorder',     'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'purchasing.vendor',            'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 5000},
    {'module_key': 'purchasing.purchasereceipt',   'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 10000},
    # Sales
    {'module_key': 'sales.customer',               'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'sales.salesorder',             'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    # Accounting
    {'module_key': 'accounting.invoice',           'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'accounting.bill',              'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'accounting.payment',           'enabled_formats': ['excel', 'csv', 'json'], 'default_format': 'excel', 'max_rows': 10000},
    {'module_key': 'accounting.journalentry',      'enabled_formats': ['excel', 'csv'],         'default_format': 'excel', 'max_rows': 10000},
]


def seed_configs(apps, schema_editor):
    ExportConfig = apps.get_model('exports', 'ExportConfig')
    for cfg in DEFAULT_CONFIGS:
        ExportConfig.objects.get_or_create(
            module_key=cfg['module_key'],
            defaults={
                'enabled_formats': cfg['enabled_formats'],
                'default_format': cfg['default_format'],
                'include_headers_default': True,
                'include_footer_default': False,
                'compress_zip_default': False,
                'date_format_default': '%Y-%m-%d',
                'max_rows': cfg['max_rows'],
                'require_staff': True,
                'is_active': True,
            }
        )


def unseed_configs(apps, schema_editor):
    ExportConfig = apps.get_model('exports', 'ExportConfig')
    module_keys = [c['module_key'] for c in DEFAULT_CONFIGS]
    ExportConfig.objects.filter(module_key__in=module_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('exports', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_configs, unseed_configs),
    ]
