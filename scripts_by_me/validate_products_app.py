# validate_products_app.py
import os
import sys
import django

# Add the project directory to the Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_dir)

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_system.settings')

# Setup Django
django.setup()

# Now import Django models
from django.apps import apps
from django.db import models

def validate_products_app():
    """Validate Products app models against expected fields"""
    
    expected_models = {
        'Unit': {
            'required_fields': ['name', 'short_name', 'code'],
            'optional_fields': ['unit_type', 'is_active', 'description', 'conversion_factor', 'base_unit']
        },
        'Brand': {
            'required_fields': ['name'],
            'optional_fields': ['slug', 'logo', 'website', 'description', 'is_active', 'is_featured', 
                               'created_at', 'updated_at', 'meta_title', 'meta_description', 'meta_keywords']
        },
        'ModelNumber': {
            'required_fields': ['name', 'code', 'brand'],
            'optional_fields': ['description', 'specifications', 'is_active', 'created_at', 'updated_at']
        },
        'ProductCategory': {
            'required_fields': ['name'],
            'optional_fields': ['slug', 'parent', 'description', 'image', 'icon', 'color', 'active', 
                               'is_featured', 'position', 'code', 'default_discount', 'tax_rate', 'notes',
                               'lft', 'rght', 'tree_id', 'level', 'meta_title', 'meta_description', 
                               'meta_keywords', 'created_by', 'updated_by', 'created_at', 'updated_at']
        },
        'PriceList': {
            'required_fields': ['name', 'code'],
            'optional_fields': ['description', 'priority', 'discount_method', 'default_discount_percentage',
                               'is_active', 'is_default', 'applicable_to_retail', 'applicable_to_wholesale',
                               'applicable_to_distributor', 'valid_from', 'valid_to', 'customer_groups',
                               'min_order_value', 'max_order_value']
        },
        'Product': {
            'required_fields': ['name', 'sku'],
            'optional_fields': ['slug', 'barcode', 'description', 'short_description', 'category', 'brand',
                               'model_number', 'product_type', 'price', 'cost', 'base_price', 'currency',
                               'default_price_list', 'base_unit', 'multi_pack', 'weight', 'dimensions',
                               'main_image', 'gallery_images', 'attributes', 'variants', 'related_products',
                               'active', 'is_featured', 'position', 'visibility', 'created_at', 'updated_at',
                               'seo_title', 'seo_description', 'seo_keywords', 'warranty_period', 'warranty_terms',
                               'returnable_days', 'shipping_class', 'free_shipping', 'hs_code', 'country_of_origin',
                               'low_stock_threshold', 'reorder_point', 'reorder_quantity', 'is_digital',
                               'digital_file', 'status', 'approved_by', 'approved_at', 'tax_class', 'is_taxable']
        },
        'ProductPrice': {
            'required_fields': ['product', 'price_list', 'price'],
            'optional_fields': ['discount_percentage', 'min_quantity', 'price_type', 'price_formula', 
                               'created_at', 'updated_at']
        },
        'ProductImage': {
            'required_fields': ['product', 'image'],
            'optional_fields': ['thumbnail', 'alt_text', 'is_primary', 'sort_order', 'created_at']
        },
        'ProductVariant': {
            'required_fields': ['product', 'sku', 'attributes'],
            'optional_fields': ['price_adjustment', 'stock_quantity', 'image', 'is_active', 
                               'created_at', 'updated_at']
        },
        'ProductReview': {
            'required_fields': ['product', 'rating', 'review'],
            'optional_fields': ['user', 'title', 'pros', 'cons', 'verified_purchase', 
                               'helpful_count', 'status', 'created_at', 'updated_at']
        }
    }
    
    print("=" * 80)
    print("🔍 VALIDATING PRODUCTS APP MODELS")
    print("=" * 80)
    
    issues_found = False
    
    # Check if products app exists
    try:
        apps.get_app_config('products')
    except LookupError:
        print("❌ Products app not found in INSTALLED_APPS!")
        return
    
    for model_name, expected in expected_models.items():
        try:
            model = apps.get_model('products', model_name)
            print(f"\n📦 Checking {model_name}...")
            
            actual_fields = [field.name for field in model._meta.get_fields()]
            actual_field_names = [f.name for f in model._meta.fields]  # Only database fields
            
            # Check required fields
            missing_required = []
            for field in expected['required_fields']:
                if field not in actual_field_names:
                    missing_required.append(field)
            
            if missing_required:
                issues_found = True
                for field in missing_required:
                    print(f"  ❌ Missing REQUIRED field: {field}")
            else:
                print(f"  ✅ All required fields present")
            
            # Check optional fields (just info, not issues)
            for field in expected['optional_fields']:
                if field not in actual_field_names:
                    print(f"  ℹ️  Missing optional field: {field}")
            
            # Check for unexpected fields
            all_expected = expected['required_fields'] + expected['optional_fields']
            unexpected = []
            for field in actual_field_names:
                if field not in all_expected and not field.startswith('_'):
                    # Skip automatic fields
                    if field not in ['id']:
                        unexpected.append(field)
            
            if unexpected:
                print(f"  📝 Unexpected fields: {', '.join(unexpected)}")
            
            # Show field count
            print(f"  📊 Total fields: {len(actual_field_names)}")
                
        except LookupError:
            issues_found = True
            print(f"  ⚠️  Model {model_name} not found in products app!")
    
    if not issues_found:
        print("\n✅ All models validated successfully!")
    else:
        print("\n⚠️  Some issues were found. Review the messages above.")

if __name__ == "__main__":
    # Verify settings module
    print(f"Using settings module: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
    validate_products_app()