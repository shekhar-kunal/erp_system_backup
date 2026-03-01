#!/usr/bin/env python
"""
Setup script to create initial test data
Run with: python setup_test_data.py
"""

import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Country, Region, City
from products.models import Product, Unit, ProductCategory, Brand, Currency
from inventory.models import Warehouse


def setup_data():
    print("=" * 50)
    print("SETTING UP TEST DATA")
    print("=" * 50)
    
    # Create Country - First try to get existing, then create if doesn't exist
    try:
        country = Country.objects.get(code="US")
        print(f"✓ Using existing country: {country.name} (Code: {country.code})")
    except Country.DoesNotExist:
        try:
            country = Country.objects.get(iso_code="US")
            print(f"✓ Using existing country: {country.name} (ISO: {country.iso_code})")
        except Country.DoesNotExist:
            country, created = Country.objects.get_or_create(
                name="United States",
                defaults={
                    'code': "US",
                    'iso_code': "US",
                    'phone_code': "1",
                    'currency': "USD",
                    'currency_symbol': "$",
                    'default_timezone': "America/New_York",
                    'is_active': True,
                    'position': 1
                }
            )
            if created:
                print(f"✓ Country created: {country.name}")
            else:
                print(f"✓ Using existing country: {country.name}")
    
    # Create Region
    try:
        region = Region.objects.get(name="New York", country=country)
        print(f"✓ Using existing region: {region.name}")
    except Region.DoesNotExist:
        region = Region.objects.create(
            name="New York",
            country=country,
            code="NY",
            is_active=True,
            position=1
        )
        print(f"✓ Region created: {region.name}")
    
    # Create City
    try:
        city = City.objects.get(name="New York City", country=country)
        print(f"✓ Using existing city: {city.name}")
    except City.DoesNotExist:
        city = City.objects.create(
            name="New York City",
            country=country,
            region=region,
            state="New York",
            timezone="America/New_York",
            postal_code="10001",
            is_active=True,
            is_capital=False,
            position=1
        )
        print(f"✓ City created: {city.name}")
    
    # Create or get Currency
    try:
        currency = Currency.objects.get(code="USD")
        print(f"✓ Using existing currency: {currency.name} ({currency.code})")
    except Currency.DoesNotExist:
        currency = Currency.objects.create(
            name="US Dollar",
            code="USD",
            symbol="$",
            is_active=True
        )
        print(f"✓ Currency created: {currency.name}")
    
    # Create Unit - Check for existing unit first
    unit = None
    try:
        unit = Unit.objects.get(code="pc")
        print(f"✓ Using existing unit: {unit.name} (Code: {unit.code})")
    except Unit.DoesNotExist:
        try:
            unit = Unit.objects.get(name="Piece")
            print(f"✓ Using existing unit by name: {unit.name}")
        except Unit.DoesNotExist:
            try:
                unit = Unit.objects.create(
                    name="Piece",
                    short_name="pc",
                    code="pc",
                    unit_type="standard",
                    is_active=True,
                    description="Piece unit for testing"
                )
                print(f"✓ Unit created: {unit.name}")
            except Exception as e:
                print(f"⚠ Could not create unit: {e}")
                # Try to get any existing unit as fallback
                unit = Unit.objects.first()
                if unit:
                    print(f"✓ Using fallback unit: {unit.name}")
    
    if not unit:
        print("⚠ No unit available. Creating a unique unit...")
        import random
        unit = Unit.objects.create(
            name=f"Piece_{random.randint(1000, 9999)}",
            short_name="pc",
            code=f"pc_{random.randint(1000, 9999)}",
            unit_type="standard",
            is_active=True
        )
        print(f"✓ Created unique unit: {unit.name}")
    
    # Create Brand
    try:
        brand = Brand.objects.get(name="Test Brand")
        print(f"✓ Using existing brand: {brand.name}")
    except Brand.DoesNotExist:
        brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand",
            description="Test brand for purchasing module",
            is_active=True,
            is_featured=False,
            website="https://testbrand.com"
        )
        print(f"✓ Brand created: {brand.name}")
    
    # Create Product Category
    try:
        category = ProductCategory.objects.get(name="Test Category")
        print(f"✓ Using existing category: {category.name}")
    except ProductCategory.DoesNotExist:
        category = ProductCategory.objects.create(
            name="Test Category",
            slug="test-category",
            description="Test category for purchasing module",
            active=True,
            is_featured=False,
            position=1,
            color="#FF5733",
            default_discount=0,
            tax_rate=0
        )
        print(f"✓ Category created: {category.name}")
    
    # Create Products - with correct fields from your model
    print("\nCreating test products...")
    products_created = 0
    
    for i in range(1, 4):
        try:
            # Check if product already exists
            product, created = Product.objects.get_or_create(
                sku=f"TP00{i}",
                defaults={
                    'name': f"Test Product {i}",
                    'description': f"Test product {i} for purchasing module testing",
                    'category': category,
                    'brand': brand,
                    'base_unit': unit,
                    'price': 100.00 * i,
                    'cost': 50.00 * i,
                    'active': True,
                    'is_featured': False,
                    'product_type': "simple",
                    'currency': currency,  # Now this is a Currency object, not a string
                    'notes': f"Test product {i} notes",
                    'multi_pack': 1,
                    'base_price': 100.00 * i
                }
            )
            if created:
                products_created += 1
                print(f"  ✓ Created: {product.name} (SKU: {product.sku})")
            else:
                print(f"  ✓ Using existing: {product.name}")
        except Exception as e:
            print(f"  ⚠ Error with product {i}: {e}")
    
    if products_created > 0:
        print(f"  Created {products_created} new products")
    
    # Create Warehouse
    try:
        warehouse, created = Warehouse.objects.get_or_create(
            code="WH001",
            defaults={
                'name': "Main Warehouse",
                'warehouse_type': "main",
                'temperature_zone': "ambient",
                'address': "123 Warehouse St, New York, NY 10001",
                'phone': "+1234567890",
                'email': "warehouse@example.com",
                'capacity': 10000.00,
                'utilization_threshold': 85.0,
                'is_active': True,
                'operating_hours': {
                    'monday': '9:00-17:00',
                    'tuesday': '9:00-17:00',
                    'wednesday': '9:00-17:00',
                    'thursday': '9:00-17:00',
                    'friday': '9:00-17:00',
                    'saturday': 'closed',
                    'sunday': 'closed'
                },
                'meta_data': {},
                'notes': "Main warehouse for testing"
            }
        )
        if created:
            print(f"\n✓ Warehouse created: {warehouse.name} ({warehouse.code})")
        else:
            print(f"\n✓ Using existing warehouse: {warehouse.name}")
    except Exception as e:
        print(f"\n⚠ Error with warehouse: {e}")
        try:
            # Try without operating_hours if it's causing issues
            warehouse, created = Warehouse.objects.get_or_create(
                code="WH001",
                defaults={
                    'name': "Main Warehouse",
                    'warehouse_type': "main",
                    'temperature_zone': "ambient",
                    'address': "123 Warehouse St, New York, NY 10001",
                    'phone': "+1234567890",
                    'email': "warehouse@example.com",
                    'capacity': 10000.00,
                    'utilization_threshold': 85.0,
                    'is_active': True,
                    'operating_hours': {},  # Empty dict as default
                    'meta_data': {},
                    'notes': "Main warehouse for testing"
                }
            )
            if created:
                print(f"\n✓ Warehouse created (without operating hours): {warehouse.name}")
            else:
                print(f"\n✓ Using existing warehouse: {warehouse.name}")
        except Exception as e2:
            print(f"\n⚠ Still having warehouse issues: {e2}")
            # Try to get any existing warehouse
            warehouse = Warehouse.objects.first()
            if warehouse:
                print(f"✓ Using existing warehouse: {warehouse.name}")
            else:
                print("⚠ No warehouse available. Purchasing tests may fail.")
                warehouse = None
    
    print("\n" + "=" * 50)
    print("✓ TEST DATA SETUP COMPLETE!")
    print("=" * 50)
    print("\nYou can now run: python test_purchasing.py")
    
    return {
        'country': country,
        'region': region,
        'city': city,
        'unit': unit,
        'brand': brand,
        'category': category,
        'warehouse': warehouse,
        'currency': currency
    }


if __name__ == "__main__":
    setup_data()