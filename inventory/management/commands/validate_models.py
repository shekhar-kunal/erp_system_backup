# products/management/commands/validate_fields.py
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models

class Command(BaseCommand):
    help = 'Validate all model fields in the products app'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            default='products',
            help='App to validate (default: products)'
        )

    def handle(self, *args, **options):
        app_name = options['app']
        self.stdout.write(self.style.SUCCESS(f'🔍 Validating {app_name} app...\n'))
        
        try:
            app_config = apps.get_app_config(app_name)
        except LookupError:
            self.stdout.write(self.style.ERROR(f'App {app_name} not found!'))
            return
        
        for model in app_config.get_models():
            self.validate_model(model)
    
    def validate_model(self, model):
        self.stdout.write(f"\n📦 Model: {model.__name__}")
        self.stdout.write("-" * 40)
        
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            
            # Check field naming
            if not field.name.isidentifier():
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  {field.name}: Invalid Python identifier"
                ))
            
            # Check CharField max_length
            if isinstance(field, models.CharField) and not field.max_length:
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  {field.name}: CharField missing max_length"
                ))
            
            # Check DecimalField
            if isinstance(field, models.DecimalField):
                if not field.max_digits:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️  {field.name}: DecimalField missing max_digits"
                    ))
                if not field.decimal_places:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️  {field.name}: DecimalField missing decimal_places"
                    ))
            
            # Show field info
            self.stdout.write(f"  • {field.name}: {field.get_internal_type()}")
        
        self.stdout.write(self.style.SUCCESS(f"  ✅ {len(model._meta.fields)} fields checked"))