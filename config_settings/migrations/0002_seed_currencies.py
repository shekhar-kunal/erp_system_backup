"""
Data migration: seed default currencies.
These must exist before the setup wizard runs.
"""
from decimal import Decimal
from django.db import migrations


CURRENCIES = [
    # code, name,                      symbol, rate,   is_base, dec_places, sym_pos, dec_sep, thou_sep
    ('USD', 'US Dollar',               '$',    '1.0000', True,  2, 'before', '.',  ','),
    ('EUR', 'Euro',                    '€',    '0.9200', False, 2, 'before', ',',  '.'),
    ('GBP', 'British Pound',           '£',    '0.7900', False, 2, 'before', '.',  ','),
    ('UAH', 'Ukrainian Hryvnia',       '₴',    '41.200', False, 2, 'after',  ',',  ' '),
    ('INR', 'Indian Rupee',            '₹',    '83.500', False, 2, 'before', '.',  ','),
    ('CNY', 'Chinese Yuan',            '¥',    '7.2400', False, 2, 'before', '.',  ','),
    ('RUB', 'Russian Ruble',           '₽',    '90.000', False, 2, 'after',  ',',  ' '),
    ('AED', 'UAE Dirham',              'د.إ',  '3.6730', False, 2, 'before', '.',  ','),
    ('JPY', 'Japanese Yen',            '¥',    '149.50', False, 0, 'before', '.',  ','),
    ('CAD', 'Canadian Dollar',         'C$',   '1.3600', False, 2, 'before', '.',  ','),
    ('AUD', 'Australian Dollar',       'A$',   '1.5300', False, 2, 'before', '.',  ','),
    ('CHF', 'Swiss Franc',             'Fr',   '0.8900', False, 2, 'before', '.',  "'"),
    ('SGD', 'Singapore Dollar',        'S$',   '1.3500', False, 2, 'before', '.',  ','),
    ('SAR', 'Saudi Riyal',             '﷼',    '3.7500', False, 2, 'before', '.',  ','),
    ('TRY', 'Turkish Lira',            '₺',    '32.000', False, 2, 'after',  ',',  '.'),
]


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model('config_settings', 'Currency')
    for code, name, symbol, rate, is_base, dec_places, sym_pos, dec_sep, thou_sep in CURRENCIES:
        Currency.objects.get_or_create(
            code=code,
            defaults=dict(
                name=name,
                symbol=symbol,
                exchange_rate=Decimal(rate),
                is_base=is_base,
                is_active=True,
                decimal_places=dec_places,
                symbol_position=sym_pos,
                decimal_separator=dec_sep,
                thousand_separator=thou_sep,
            )
        )


def remove_currencies(apps, schema_editor):
    Currency = apps.get_model('config_settings', 'Currency')
    Currency.objects.filter(code__in=[c[0] for c in CURRENCIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('config_settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_currencies, remove_currencies),
    ]
