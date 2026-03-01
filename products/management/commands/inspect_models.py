from django.core.management.base import BaseCommand
from django.apps import apps
import inspect


class Command(BaseCommand):
    help = 'Inspect all purchasing-related models and their fields'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            help='Specific app to inspect (e.g., purchasing, products, core)',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Specific model to inspect',
        )

    def handle(self, *args, **options):
        app_name = options.get('app')
        model_name = options.get('model')
        
        if app_name and model_name:
            self.inspect_model(app_name, model_name)
        elif app_name:
            self.inspect_app(app_name)
        else:
            self.inspect_all()
    
    def inspect_model(self, app_name, model_name):
        """Inspect a specific model"""
        try:
            model = apps.get_model(app_name, model_name)
            self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
            self.stdout.write(self.style.SUCCESS(f"MODEL: {app_name}.{model_name}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))
            
            # Get all fields
            fields = model._meta.get_fields()
            
            self.stdout.write("FIELDS:")
            for field in fields:
                if field.auto_created and not field.concrete:
                    continue
                
                # Get field properties
                field_type = field.__class__.__name__
                required = not field.null if hasattr(field, 'null') else 'N/A'
                max_length = getattr(field, 'max_length', 'N/A')
                default = getattr(field, 'default', 'N/A')
                
                self.stdout.write(f"  - {field.name}")
                self.stdout.write(f"    Type: {field_type}")
                self.stdout.write(f"    Required: {required}")
                if max_length != 'N/A':
                    self.stdout.write(f"    Max Length: {max_length}")
                if default != 'N/A' and default != 'NOT PROVIDED':
                    self.stdout.write(f"    Default: {default}")
                self.stdout.write("")
            
            # Show model constraints
            constraints = model._meta.constraints
            if constraints:
                self.stdout.write("\nCONSTRAINTS:")
                for constraint in constraints:
                    self.stdout.write(f"  - {constraint}")
            
            # Show unique together
            if model._meta.unique_together:
                self.stdout.write("\nUNIQUE TOGETHER:")
                for unique in model._meta.unique_together:
                    self.stdout.write(f"  - {unique}")
            
            # Show indexes
            if model._meta.indexes:
                self.stdout.write("\nINDEXES:")
                for index in model._meta.indexes:
                    self.stdout.write(f"  - {index}")
            
        except LookupError as e:
            self.stdout.write(self.style.ERROR(f"Model not found: {e}"))
    
    def inspect_app(self, app_name):
        """Inspect all models in an app"""
        try:
            app_config = apps.get_app_config(app_name)
            self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
            self.stdout.write(self.style.SUCCESS(f"APP: {app_name}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*80}"))
            
            for model in app_config.get_models():
                self.inspect_model(app_name, model.__name__)
                
        except LookupError:
            self.stdout.write(self.style.ERROR(f"App not found: {app_name}"))
    
    def inspect_all(self):
        """Inspect all relevant models"""
        apps_to_inspect = ['purchasing', 'products', 'inventory', 'core']
        models_to_inspect = [
            ('purchasing', 'Vendor'),
            ('purchasing', 'PurchaseOrder'),
            ('purchasing', 'PurchaseOrderLine'),
            ('purchasing', 'PurchaseReceipt'),
            ('purchasing', 'PurchaseReceiptLine'),
            ('purchasing', 'PurchasingSettings'),
            ('purchasing', 'PurchaseOrderHistory'),
            ('products', 'Product'),
            ('products', 'Unit'),
            ('products', 'ProductCategory'),
            ('products', 'Brand'),
            ('inventory', 'Warehouse'),
            ('inventory', 'WarehouseSection'),
            ('inventory', 'Stock'),
            ('inventory', 'StockBatch'),
            ('core', 'Country'),
            ('core', 'Region'),
            ('core', 'City'),
        ]
        
        for app, model in models_to_inspect:
            self.inspect_model(app, model)