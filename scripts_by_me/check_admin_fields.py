#!/usr/bin/env python
"""
Script to check for mismatches between admin list_display and model fields
Run with: python check_admin_fields.py
"""

import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.apps import apps
from django.contrib import admin
import inspect


def get_admin_classes():
    """Get all registered admin classes"""
    admin_classes = []
    for model, model_admin in admin.site._registry.items():
        admin_classes.append({
            'app': model._meta.app_label,
            'model': model.__name__,
            'admin_class': model_admin.__class__.__name__,
            'admin_instance': model_admin,
            'model_instance': model
        })
    return admin_classes


def safe_get_attr(obj, attr_name):
    """Safely get attribute, handling non-string values"""
    if not isinstance(attr_name, str):
        return None
    return getattr(obj, attr_name, None)


def check_list_display(admin_info):
    """Check if list_display fields exist in the model"""
    admin_instance = admin_info['admin_instance']
    model = admin_info['model_instance']
    
    if not hasattr(admin_instance, 'list_display'):
        return []
    
    list_display = admin_instance.list_display
    model_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
    
    # Get all model properties and methods
    model_attrs = [name for name in dir(model) if not name.startswith('_')]
    
    issues = []
    for field_name in list_display:
        if not isinstance(field_name, str):
            issues.append({
                'type': 'list_display',
                'field': str(field_name),
                'message': f"Non-string value in list_display: {field_name}"
            })
            continue
        
        # Skip if it's a method on the admin class
        if hasattr(admin_instance, field_name) and callable(getattr(admin_instance, field_name)):
            continue
        
        # Skip if it's a property or method on the model
        if field_name in model_attrs:
            continue
        
        # Check if it's a model field
        if field_name not in model_fields:
            issues.append({
                'type': 'list_display',
                'field': field_name,
                'message': f"'{field_name}' is not a field in {admin_info['model']}"
            })
    
    return issues


def check_readonly_fields(admin_info):
    """Check if readonly_fields fields exist in the model"""
    admin_instance = admin_info['admin_instance']
    model = admin_info['model_instance']
    
    if not hasattr(admin_instance, 'readonly_fields'):
        return []
    
    readonly_fields = admin_instance.readonly_fields
    if isinstance(readonly_fields, str):
        readonly_fields = [readonly_fields]
    
    model_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
    
    issues = []
    for field_name in readonly_fields:
        if not isinstance(field_name, str):
            continue
        
        if field_name not in model_fields:
            issues.append({
                'type': 'readonly_fields',
                'field': field_name,
                'message': f"'{field_name}' is not a field in {admin_info['model']}"
            })
    
    return issues


def check_list_filter(admin_info):
    """Check if list_filter fields exist in the model"""
    admin_instance = admin_info['admin_instance']
    model = admin_info['model_instance']
    
    if not hasattr(admin_instance, 'list_filter'):
        return []
    
    list_filter = admin_instance.list_filter
    model_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
    
    issues = []
    for item in list_filter:
        # Handle tuples (like ('field', SimpleListFilter))
        if isinstance(item, tuple):
            field_name = item[0] if len(item) > 0 and isinstance(item[0], str) else None
        elif isinstance(item, str):
            field_name = item
        else:
            # Skip non-string values (like filter classes)
            continue
        
        if field_name and field_name not in model_fields and not hasattr(model, field_name):
            issues.append({
                'type': 'list_filter',
                'field': field_name,
                'message': f"'{field_name}' is not a field in {admin_info['model']}"
            })
    
    return issues


def check_search_fields(admin_info):
    """Check if search_fields exist in the model"""
    admin_instance = admin_info['admin_instance']
    model = admin_info['model_instance']
    
    if not hasattr(admin_instance, 'search_fields'):
        return []
    
    search_fields = admin_instance.search_fields
    model_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
    
    issues = []
    for field_name in search_fields:
        if not isinstance(field_name, str):
            continue
        
        # Handle related field lookups (e.g., 'product__name')
        if '__' in field_name:
            base_field = field_name.split('__')[0]
            if base_field not in model_fields:
                issues.append({
                    'type': 'search_fields',
                    'field': field_name,
                    'message': f"'{base_field}' (from '{field_name}') is not a field in {admin_info['model']}"
                })
        elif field_name not in model_fields:
            issues.append({
                'type': 'search_fields',
                'field': field_name,
                'message': f"'{field_name}' is not a field in {admin_info['model']}"
            })
    
    return issues


def check_date_hierarchy(admin_info):
    """Check if date_hierarchy exists in the model"""
    admin_instance = admin_info['admin_instance']
    model = admin_info['model_instance']
    
    if not hasattr(admin_instance, 'date_hierarchy'):
        return []
    
    field_name = admin_instance.date_hierarchy
    if not field_name or not isinstance(field_name, str):
        return []
    
    model_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
    
    if field_name not in model_fields:
        return [{
            'type': 'date_hierarchy',
            'field': field_name,
            'message': f"'{field_name}' is not a field in {admin_info['model']}"
        }]
    
    return []


def print_model_fields(model):
    """Print all fields of a model for debugging"""
    print(f"\nFields in {model.__name__}:")
    for field in model._meta.get_fields():
        if not field.auto_created:
            print(f"  - {field.name}: {field.__class__.__name__}")


def main():
    print("=" * 80)
    print("CHECKING ADMIN VS MODEL FIELD MISMATCHES")
    print("=" * 80)
    
    admin_classes = get_admin_classes()
    all_issues = []
    
    for admin_info in admin_classes:
        print(f"\nChecking {admin_info['app']}.{admin_info['model']} (admin: {admin_info['admin_class']})")
        
        issues = []
        issues.extend(check_list_display(admin_info))
        issues.extend(check_readonly_fields(admin_info))
        issues.extend(check_list_filter(admin_info))
        issues.extend(check_search_fields(admin_info))
        issues.extend(check_date_hierarchy(admin_info))
        
        if issues:
            print(f"  Found {len(issues)} issues:")
            for issue in issues:
                print(f"    ❌ {issue['type']}: {issue['message']}")
                all_issues.append(issue)
        else:
            print("  ✅ No issues found")
    
    print("\n" + "=" * 80)
    print(f"SUMMARY: Found {len(all_issues)} total issues")
    print("=" * 80)
    
    if all_issues:
        print("\nIssues by type:")
        issue_types = {}
        for issue in all_issues:
            issue_types[issue['type']] = issue_types.get(issue['type'], 0) + 1
        
        for issue_type, count in issue_types.items():
            print(f"  {issue_type}: {count}")
    
    return len(all_issues)


if __name__ == "__main__":
    sys.exit(main())