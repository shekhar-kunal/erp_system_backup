# list_all_fields.py
import os
import sys
import django

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Print debug info
print(f"Current directory: {current_dir}")
print(f"Python path: {sys.path}")
print(f"Looking for config.settings...")

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Verify we can import the settings
try:
    __import__('config.settings')
    print("✅ Successfully found config.settings")
except ImportError as e:
    print(f"❌ Error importing config.settings: {e}")
    sys.exit(1)

# Setup Django
django.setup()

# Now import Django models
from django.apps import apps
from django.db import models

def get_field_info(field):
    """Safely get field information, handling relation fields"""
    
    # Determine field type
    if field.is_relation:
        if field.many_to_one:
            field_type = "ForeignKey"
        elif field.many_to_many:
            field_type = "ManyToManyField"
        elif field.one_to_one:
            field_type = "OneToOneField"
        else:
            field_type = "Relation"
    else:
        field_type = field.get_internal_type() if hasattr(field, 'get_internal_type') else type(field).__name__
    
    # Safely get attributes (only for concrete fields, not relations)
    options = []
    
    # Only concrete fields have these attributes
    if not field.is_relation:
        if hasattr(field, 'max_length') and field.max_length:
            options.append(f"max_length={field.max_length}")
        if hasattr(field, 'null') and field.null:
            options.append("null=True")
        if hasattr(field, 'blank') and field.blank:
            options.append("blank=True")
        if hasattr(field, 'unique') and field.unique:
            options.append("unique=True")
        if hasattr(field, 'default') and field.default != models.fields.NOT_PROVIDED:
            if field.default and not callable(field.default):
                options.append(f"default={field.default}")
    
    # For ForeignKey, show related model
    if field.is_relation and hasattr(field, 'related_model') and field.related_model:
        related_model_name = field.related_model.__name__
        field_type = f"{field_type} → {related_model_name}"
    
    return field_type, options

def list_all_model_fields():
    """List all fields from all models in the project"""
    
    print("=" * 80)
    print("📊 ALL MODEL FIELDS IN PROJECT")
    print("=" * 80)
    
    all_models = apps.get_models()
    
    for model in sorted(all_models, key=lambda x: x._meta.app_label):
        app_label = model._meta.app_label
        model_name = model.__name__
        
        print(f"\n📁 {app_label}.{model_name}")
        print("-" * 60)
        
        # Get all fields
        all_fields = model._meta.get_fields()
        
        # Separate concrete fields and relations for better display
        concrete_fields = [f for f in all_fields if f.concrete and not f.auto_created]
        relation_fields = [f for f in all_fields if f.is_relation and f.concrete]
        reverse_relations = [f for f in all_fields if f.is_relation and not f.concrete]
        
        # Print concrete fields
        if concrete_fields:
            print("  📌 Concrete Fields:")
            for field in sorted(concrete_fields, key=lambda x: x.name):
                field_type, options = get_field_info(field)
                field_str = f"    • {field.name}: {field_type}"
                if options:
                    field_str += f" ({', '.join(options)})"
                print(field_str)
        
        # Print relation fields
        if relation_fields:
            print("\n  🔗 Relation Fields:")
            for field in sorted(relation_fields, key=lambda x: x.name):
                field_type, options = get_field_info(field)
                field_str = f"    • {field.name}: {field_type}"
                if options:
                    field_str += f" ({', '.join(options)})"
                print(field_str)
        
        # Print reverse relations (optional - comment out if too verbose)
        if reverse_relations and False:  # Set to True if you want to see reverse relations
            print("\n  🔄 Reverse Relations:")
            for field in sorted(reverse_relations, key=lambda x: x.name):
                field_type, _ = get_field_info(field)
                print(f"    • {field.name}: {field_type}")
        
        # Count fields
        field_count = len(concrete_fields) + len(relation_fields)
        print(f"\n  📊 Total fields: {field_count} (Concrete: {len(concrete_fields)}, Relations: {len(relation_fields)})")
        
        # Show if model has any issues
        issues = []
        for field in concrete_fields:
            if isinstance(field, models.CharField) and not field.max_length:
                issues.append(f"CharField '{field.name}' missing max_length")
            if isinstance(field, models.DecimalField):
                if not field.max_digits:
                    issues.append(f"DecimalField '{field.name}' missing max_digits")
                if not field.decimal_places:
                    issues.append(f"DecimalField '{field.name}' missing decimal_places")
        
        if issues:
            print("\n  ⚠️  Potential Issues:")
            for issue in issues[:3]:  # Show first 3 issues
                print(f"    • {issue}")
            if len(issues) > 3:
                print(f"    • ... and {len(issues)-3} more issues")

if __name__ == "__main__":
    list_all_model_fields()