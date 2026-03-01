#!/usr/bin/env python
"""
ERP PRODUCT APP - DATA MANAGEMENT SCRIPT
Run this script to clear old data and create fresh test data
"""

import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal
import random
from django.utils import timezone
from django.db import connection

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import models
from products.models import (
    Unit, Brand, ModelNumber, ProductCategory, PriceList,
    Product, ProductPrice, ProductAttribute, ProductAttributeValue,
    ProductAttributeAssignment, ProductVariant, ProductPriceHistory,
    ProductPacking, ProductImage
)
from django.contrib.auth import get_user_model

User = get_user_model()

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}📌 {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")

class ERPDataManager:
    """Manage ERP product data - clear old and create new test data"""
    
    def __init__(self):
        self.test_data = {}
        
    def clear_all_data(self, confirm=True):
        """Clear all existing data from product-related tables"""
        print_header("CLEARING OLD DATA")
        
        if confirm:
            response = input(f"{Colors.YELLOW}⚠️  This will DELETE ALL existing product data. Are you sure? (yes/no): {Colors.END}")
            if response.lower() != 'yes':
                print_warning("Operation cancelled")
                return False
        
        # Order matters due to foreign key constraints
        deletion_order = [
            (ProductPriceHistory, "Price history"),
            (ProductPrice, "Product prices"),
            (ProductVariant, "Product variants"),
            (ProductAttributeAssignment, "Attribute assignments"),
            (ProductPacking, "Product packing"),
            (ProductImage, "Product images"),
            (Product, "Products"),
            (ModelNumber, "Model numbers"),
            (PriceList, "Price lists"),
            (ProductCategory, "Categories"),
            (Brand, "Brands"),
            (ProductAttributeValue, "Attribute values"),
            (ProductAttribute, "Attributes"),
            (Unit, "Units"),
        ]
        
        for model, description in deletion_order:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                print_success(f"Deleted {count} {description}")
            else:
                print_info(f"No {description} to delete")
        
        # Reset SQLite sequences if using SQLite
        if 'sqlite' in connection.settings_dict['ENGINE']:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sqlite_sequence")
            print_success("Reset SQLite sequences")
        
        print_success("All data cleared successfully!")
        return True
    
    def create_base_data(self):
        """Create base data (units, attributes, brands, categories, price lists)"""
        print_header("CREATING BASE DATA")
        
        # 1. Create Units
        units = [
            {'name': 'Piece', 'short_name': 'pc', 'code': 'PC', 'unit_type': 'quantity'},
            {'name': 'Kilogram', 'short_name': 'kg', 'code': 'KG', 'unit_type': 'weight'},
            {'name': 'Liter', 'short_name': 'L', 'code': 'LTR', 'unit_type': 'volume'},
            {'name': 'Meter', 'short_name': 'm', 'code': 'M', 'unit_type': 'length'},
            {'name': 'Box', 'short_name': 'box', 'code': 'BOX', 'unit_type': 'packaging'},
            {'name': 'Set', 'short_name': 'set', 'code': 'SET', 'unit_type': 'quantity'},
        ]
        
        created_units = []
        for unit_data in units:
            unit, created = Unit.objects.get_or_create(
                code=unit_data['code'],
                defaults=unit_data
            )
            created_units.append(unit)
            print_success(f"Unit: {unit.name} ({'created' if created else 'existing'})")
        
        # 2. Create Attributes - FIXED: Added unique codes
        attributes = [
            {'name': 'Color', 'code': 'COLOR', 'type': 'text', 'values': ['Red', 'Blue', 'Black', 'White', 'Green', 'Yellow', 'Purple', 'Orange']},
            {'name': 'Size', 'code': 'SIZE', 'type': 'text', 'values': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']},
            {'name': 'Material', 'code': 'MAT', 'type': 'text', 'values': ['Cotton', 'Polyester', 'Leather', 'Plastic', 'Metal', 'Wood', 'Glass']},
            {'name': 'Weight', 'code': 'WGT', 'type': 'float', 'values': ['0.5kg', '1kg', '2kg', '5kg', '10kg']},
            {'name': 'Voltage', 'code': 'VOLT', 'type': 'integer', 'values': ['110V', '220V', '12V']},
            {'name': 'Warranty', 'code': 'WAR', 'type': 'text', 'values': ['1 Year', '2 Years', '3 Years', '5 Years']},
        ]
        
        attr_objects = {}
        for attr_data in attributes:
            try:
                # Create with unique code
                attr, created = ProductAttribute.objects.get_or_create(
                    code=attr_data['code'],
                    defaults={
                        'name': attr_data['name'],
                    }
                )
                
                # Set other fields if they exist
                if hasattr(attr, 'attribute_type'):
                    attr.attribute_type = attr_data['type']
                if hasattr(attr, 'is_required'):
                    attr.is_required = True
                if hasattr(attr, 'is_variant_defining'):
                    attr.is_variant_defining = attr_data['name'] in ['Color', 'Size']
                if hasattr(attr, 'display_order'):
                    attr.display_order = len(attr_objects) + 1
                
                attr.save()
                attr_objects[attr_data['name']] = attr
                print_success(f"Attribute: {attr.name} (code: {attr.code})")
                
                # Create attribute values
                for value in attr_data['values']:
                    val, _ = ProductAttributeValue.objects.get_or_create(
                        attribute=attr,
                        value=value,
                        defaults={'code': value[:3].upper() if hasattr(ProductAttributeValue, 'code') else value[:3].upper()}
                    )
                
            except Exception as e:
                print_warning(f"Could not create attribute {attr_data['name']}: {e}")
        
        # 3. Create Brands - FIXED: Removed duplicate Sony
        brands = [
            {'name': 'Apple', 'slug': 'apple', 'website': 'https://apple.com'},
            {'name': 'Samsung', 'slug': 'samsung', 'website': 'https://samsung.com'},
            {'name': 'Sony', 'slug': 'sony', 'website': 'https://sony.com'},
            {'name': 'LG', 'slug': 'lg', 'website': 'https://lg.com'},
            {'name': 'Dell', 'slug': 'dell', 'website': 'https://dell.com'},
            {'name': 'HP', 'slug': 'hp', 'website': 'https://hp.com'},
            {'name': 'Lenovo', 'slug': 'lenovo', 'website': 'https://lenovo.com'},
            {'name': 'Microsoft', 'slug': 'microsoft', 'website': 'https://microsoft.com'},
            {'name': 'Google', 'slug': 'google', 'website': 'https://google.com'},
            {'name': 'Amazon', 'slug': 'amazon', 'website': 'https://amazon.com'},
            {'name': 'Nike', 'slug': 'nike', 'website': 'https://nike.com'},
            {'name': 'Adidas', 'slug': 'adidas', 'website': 'https://adidas.com'},
            {'name': 'Puma', 'slug': 'puma', 'website': 'https://puma.com'},
            {'name': 'Panasonic', 'slug': 'panasonic', 'website': 'https://panasonic.com'},
            {'name': 'Canon', 'slug': 'canon', 'website': 'https://canon.com'},
        ]
        
        brand_objects = []
        for brand_data in brands:
            try:
                brand, created = Brand.objects.get_or_create(
                    name=brand_data['name'],  # Use name as lookup since it's unique
                    defaults={
                        'slug': brand_data['slug'],
                        'website': brand_data['website'],
                        'is_active': True,
                        'is_featured': random.choice([True, False])
                    }
                )
                brand_objects.append(brand)
                print_success(f"Brand: {brand.name}")
            except Exception as e:
                print_warning(f"Could not create brand {brand_data['name']}: {e}")
        
        # 4. Create Categories (with hierarchy)
        categories = [
            {'name': 'Electronics', 'code': 'ELEC', 'children': [
                {'name': 'Smartphones', 'code': 'PHONE', 'children': [
                    {'name': 'Android Phones', 'code': 'ANDROID'},
                    {'name': 'iOS Phones', 'code': 'IOS'},
                ]},
                {'name': 'Laptops', 'code': 'LAPTOP', 'children': [
                    {'name': 'Gaming Laptops', 'code': 'GAMING'},
                    {'name': 'Business Laptops', 'code': 'BUSINESS'},
                    {'name': 'Ultrabooks', 'code': 'ULTRA'},
                ]},
                {'name': 'Tablets', 'code': 'TABLET'},
                {'name': 'Accessories', 'code': 'ACC', 'children': [
                    {'name': 'Cables', 'code': 'CABLE'},
                    {'name': 'Chargers', 'code': 'CHARGER'},
                    {'name': 'Cases', 'code': 'CASE'},
                ]},
            ]},
            {'name': 'Clothing', 'code': 'CLOTH', 'children': [
                {'name': 'Men', 'code': 'MEN', 'children': [
                    {'name': 'Shirts', 'code': 'M-SHIRT'},
                    {'name': 'Pants', 'code': 'M-PANT'},
                    {'name': 'Jackets', 'code': 'M-JACKET'},
                ]},
                {'name': 'Women', 'code': 'WOMEN', 'children': [
                    {'name': 'Dresses', 'code': 'W-DRESS'},
                    {'name': 'Skirts', 'code': 'W-SKIRT'},
                    {'name': 'Blouses', 'code': 'W-BLOUSE'},
                ]},
                {'name': 'Kids', 'code': 'KIDS'},
            ]},
            {'name': 'Home & Garden', 'code': 'HOME', 'children': [
                {'name': 'Furniture', 'code': 'FURN'},
                {'name': 'Kitchen', 'code': 'KITCHEN'},
                {'name': 'Garden', 'code': 'GARDEN'},
            ]},
        ]
        
        def create_category_tree(parent, children_data):
            for child_data in children_data:
                child, _ = ProductCategory.objects.get_or_create(
                    code=child_data['code'],
                    defaults={
                        'name': child_data['name'],
                        'parent': parent,
                        'active': True,
                        'default_discount': random.randint(0, 15),
                        'tax_rate': random.choice([5, 12, 18, 28])
                    }
                )
                if 'children' in child_data:
                    create_category_tree(child, child_data['children'])
        
        for cat_data in categories:
            parent, _ = ProductCategory.objects.get_or_create(
                code=cat_data['code'],
                defaults={
                    'name': cat_data['name'],
                    'parent': None,
                    'active': True,
                    'default_discount': random.randint(0, 10),
                    'tax_rate': random.choice([5, 12, 18])
                }
            )
            if 'children' in cat_data:
                create_category_tree(parent, cat_data['children'])
        
        print_success(f"Categories created with hierarchy")
        
        # 5. Create PriceLists
        price_lists = {}
        price_list_configs = [
            ('Retail', 'RETAIL', 1, 0, True, True, False, False),
            ('Wholesale', 'WHOLESALE', 2, 15, False, False, True, False),
            ('Distributor', 'DISTRIBUTOR', 3, 25, False, False, False, True),
            ('Premium', 'PREMIUM', 4, 10, False, True, False, False),
            ('Export', 'EXPORT', 5, 20, False, False, False, False),
        ]
        
        for name, code, priority, discount, is_default, retail, wholesale, distributor in price_list_configs:
            # Check if fields exist before using them
            defaults = {
                'name': name,
                'priority': priority,
                'discount_method': 'percentage',
                'default_discount_percentage': discount,
                'is_active': True,
                'is_default': is_default,
            }
            
            # Add optional fields only if they exist in the model
            if hasattr(PriceList, 'applicable_to_retail'):
                defaults['applicable_to_retail'] = retail
            if hasattr(PriceList, 'applicable_to_wholesale'):
                defaults['applicable_to_wholesale'] = wholesale
            if hasattr(PriceList, 'applicable_to_distributor'):
                defaults['applicable_to_distributor'] = distributor
            
            price_list, created = PriceList.objects.get_or_create(
                code=code,
                defaults=defaults
            )
            price_lists[code.lower()] = price_list
            print_success(f"Price List: {name}")
        
        # 6. Create ModelNumbers for each brand
        model_numbers = []
        models_per_brand = ['Pro', 'Lite', 'Max', 'Ultra', 'Basic', 'Plus', 'Elite', 'Premium']
        
        for brand in brand_objects:
            for model_name in random.sample(models_per_brand, k=min(5, len(models_per_brand))):
                code = f"{brand.name[:2].upper()}{random.randint(100, 999)}"
                try:
                    model, created = ModelNumber.objects.get_or_create(
                        code=code,
                        brand=brand,
                        defaults={
                            'name': f"{brand.name} {model_name}",
                            'specifications': {
                                'year': random.randint(2022, 2026),
                                'series': model_name,
                                'rating': random.randint(1, 5)
                            }
                        }
                    )
                    model_numbers.append(model)
                except Exception as e:
                    print_warning(f"Could not create model number for {brand.name}: {e}")
        
        print_success(f"Created {len(model_numbers)} model numbers")
        
        self.test_data.update({
            'units': created_units,
            'brands': brand_objects,
            'model_numbers': model_numbers,
            'price_lists': price_lists,
            'attributes': attr_objects,
        })
        
        return self.test_data
    
    def create_products(self, count=1000):
        """Create large number of products with variants and prices"""
        print_header(f"CREATING {count} PRODUCTS")
        
        products = []
        categories = list(ProductCategory.objects.filter(active=True))
        units = list(Unit.objects.all())
        brands = list(Brand.objects.all())
        price_lists = self.test_data.get('price_lists', {})
        attributes = self.test_data.get('attributes', {})
        
        if not categories:
            print_warning("No categories found!")
            return
        if not units:
            print_warning("No units found!")
            return
        if not brands:
            print_warning("No brands found!")
            return
        
        batch_size = 100
        num_batches = (count + batch_size - 1) // batch_size
        
        for batch in range(num_batches):
            start_idx = batch * batch_size
            end_idx = min((batch + 1) * batch_size, count)
            
            print_info(f"Creating products {start_idx + 1} to {end_idx}...")
            
            batch_products = []
            for i in range(start_idx, end_idx):
                try:
                    # Select random base data
                    category = random.choice(categories)
                    brand = random.choice(brands)
                    unit = random.choice(units)
                    model_numbers_for_brand = ModelNumber.objects.filter(brand=brand)
                    if not model_numbers_for_brand.exists():
                        continue
                    model_number = random.choice(model_numbers_for_brand)
                    
                    # Get price list
                    price_list = price_lists.get('retail')
                    if not price_list:
                        price_list = PriceList.objects.filter(is_default=True).first()
                    
                    # Generate product data
                    base_price = Decimal(str(random.randint(10, 999)) + '.' + str(random.randint(0, 99)))
                    discount = random.randint(0, 30)
                    discounted_price = base_price * (Decimal('100') - Decimal(str(discount))) / Decimal('100')
                    cost = base_price * Decimal('0.6')
                    
                    # Create product
                    product = Product.objects.create(
                        name=f"{brand.name} {model_number.name} - {random.choice(['Deluxe', 'Standard', 'Pro', 'Max'])} {i+1}",
                        slug=f"{brand.slug}-{model_number.code.lower()}-{i+1}",
                        category=category,
                        brand=brand,
                        model_number=model_number,
                        base_unit=unit,
                        price=base_price,
                        discount_price=discounted_price,
                        cost=cost,
                        base_price=base_price,
                        default_price_list=price_list,
                        stock_quantity=random.randint(0, 1000),
                        reorder_level=random.randint(5, 50),
                        sku=f"SKU-{brand.name[:3].upper()}-{i+1:06d}",
                        barcode=f"{random.randint(100000000000, 999999999999)}",
                        product_type=random.choice(['STOCKABLE', 'CONSUMABLE', 'SERVICE']),
                        description=f"High quality product from {brand.name}. Features: {random.choice(['Latest model', 'Best seller', 'Premium quality', 'Eco-friendly'])}",
                        is_featured=random.choice([True, False]),
                        visibility=random.choice(['published', 'draft', 'private']),
                        is_in_stock=random.choice([True, False])
                    )
                    
                    batch_products.append(product)
                    
                    # Create product prices for different tiers
                    for tier, multiplier in [('retail', 1.0), ('wholesale', 0.85), ('distributor', 0.75)]:
                        price_list_key = tier.upper()
                        if price_list_key in price_lists:
                            tier_price_list = price_lists[price_list_key]
                            try:
                                ProductPrice.objects.create(
                                    product=product,
                                    price_list=tier_price_list,
                                    price=base_price * Decimal(str(multiplier)),
                                    discount_percentage=int((1 - multiplier) * 100),
                                    min_quantity={'retail': 1, 'wholesale': 5, 'distributor': 20}[tier],
                                    valid_from=timezone.now(),
                                    valid_to=timezone.now() + timedelta(days=365)
                                )
                            except Exception as e:
                                pass
                    
                    # Create variants for some products (30% chance)
                    if random.random() < 0.3 and attributes:
                        self.create_variants(product, attributes)
                    
                    # Create packing options (50% chance)
                    if random.random() < 0.5:
                        self.create_packing(product, unit)
                    
                    # Create price history entries (20% chance)
                    if random.random() < 0.2:
                        try:
                            ProductPriceHistory.objects.create(
                                product=product,
                                old_price=base_price * Decimal('0.9'),
                                new_price=base_price,
                                changed_by=None,
                                reason="Price update",
                                changed_at=timezone.now() - timedelta(days=random.randint(1, 30))
                            )
                        except:
                            pass
                    
                except Exception as e:
                    print_warning(f"Error creating product {i+1}: {e}")
                    continue
            
            products.extend(batch_products)
            print_success(f"Created batch {batch + 1}/{num_batches} ({len(batch_products)} products)")
        
        print_success(f"Successfully created {len(products)} products")
        return products
    
    def create_variants(self, product, attributes):
        """Create variants for a product"""
        color_attr = attributes.get('Color')
        size_attr = attributes.get('Size')
        
        if not (color_attr and size_attr):
            return
        
        # Get attribute values
        colors = list(ProductAttributeValue.objects.filter(attribute=color_attr))[:3]
        sizes = list(ProductAttributeValue.objects.filter(attribute=size_attr))[:3]
        
        for color in random.sample(colors, k=min(2, len(colors))):
            for size in random.sample(sizes, k=min(2, len(sizes))):
                try:
                    # Create assignments
                    assignment1, _ = ProductAttributeAssignment.objects.get_or_create(
                        product=product,
                        attribute=color_attr,
                        value=color
                    )
                    assignment2, _ = ProductAttributeAssignment.objects.get_or_create(
                        product=product,
                        attribute=size_attr,
                        value=size
                    )
                    
                    # Create variant
                    variant, _ = ProductVariant.objects.get_or_create(
                        product=product,
                        sku=f"{product.sku}-{color.value[:1]}{size.value[:1]}",
                        defaults={
                            'stock_quantity': random.randint(0, 50),
                            'is_active': True
                        }
                    )
                    
                    # Try to add attributes
                    if hasattr(variant, 'attributes') and hasattr(variant.attributes, 'add'):
                        variant.attributes.add(assignment1, assignment2)
                    elif hasattr(variant, 'assignment_set'):
                        variant.assignment_set.add(assignment1, assignment2)
                except Exception as e:
                    pass
    
    def create_packing(self, product, unit):
        """Create packing options for a product"""
        packing_units = [
            {'name': 'Box of 5', 'quantity': 5, 'price_mult': 4.5},
            {'name': 'Box of 10', 'quantity': 10, 'price_mult': 8.5},
            {'name': 'Case of 20', 'quantity': 20, 'price_mult': 16},
            {'name': 'Pallet', 'quantity': 100, 'price_mult': 75},
        ]
        
        try:
            packing = random.choice(packing_units)
            packing_unit, _ = Unit.objects.get_or_create(
                name="Box",
                defaults={'short_name': 'box', 'code': 'BOX', 'unit_type': 'packaging'}
            )
            
            ProductPacking.objects.get_or_create(
                product=product,
                quantity=packing['quantity'],
                defaults={
                    'packing_unit': packing_unit,
                    'price': product.price * Decimal(str(packing['price_mult'])),
                    'is_default': False
                }
            )
        except Exception as e:
            pass
    
    def print_statistics(self):
        """Print database statistics"""
        print_header("DATABASE STATISTICS")
        
        stats = [
            ("Units", Unit.objects.count()),
            ("Brands", Brand.objects.count()),
            ("Model Numbers", ModelNumber.objects.count()),
            ("Categories", ProductCategory.objects.count()),
            ("Price Lists", PriceList.objects.count()),
            ("Products", Product.objects.count()),
            ("Product Prices", ProductPrice.objects.count()),
            ("Product Variants", ProductVariant.objects.count()),
            ("Product Attributes", ProductAttribute.objects.count()),
            ("Attribute Values", ProductAttributeValue.objects.count()),
            ("Attribute Assignments", ProductAttributeAssignment.objects.count()),
            ("Product Packing", ProductPacking.objects.count()),
            ("Price History", ProductPriceHistory.objects.count()),
        ]
        
        for description, count in stats:
            print(f"{description:25}: {count:6,}")
    
    def run_full_setup(self, product_count=1000, clear_existing=True):
        """Run complete setup: clear old data, create base data, create products"""
        print_header("ERP PRODUCT APP - COMPLETE DATA SETUP")
        
        if clear_existing:
            if not self.clear_all_data(confirm=True):
                return
        
        self.create_base_data()
        self.create_products(product_count)
        self.print_statistics()
        
        print_header("SETUP COMPLETE")
        print_success(f"Successfully created {product_count}+ products with complete data")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ERP Product Data Management')
    parser.add_argument('--clear', action='store_true', help='Clear all existing data')
    parser.add_argument('--count', type=int, default=1000, help='Number of products to create (default: 1000)')
    parser.add_argument('--no-confirm', action='store_true', help='Skip confirmation prompts')
    
    args = parser.parse_args()
    
    manager = ERPDataManager()
    
    if args.clear:
        manager.clear_all_data(confirm=not args.no_confirm)
    else:
        # Run full setup
        response = input(f"{Colors.YELLOW}This will create {args.count}+ products. Continue? (yes/no): {Colors.END}")
        if response.lower() == 'yes':
            manager.run_full_setup(product_count=args.count, clear_existing=True)
        else:
            print_warning("Operation cancelled")

if __name__ == "__main__":
    main()