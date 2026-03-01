from django.core.management.base import BaseCommand
from products.models import Product
from inventory.models import Warehouse, Stock, StockMovement

class Command(BaseCommand):
    help = "Advanced stock reconciliation for multiple warehouses"

    def handle(self, *args, **options):
        self.stdout.write("Starting advanced stock reconciliation...")

        # Example: Existing stock data structure
        # old_stock_data = [
        #     {'product_sku': 'PROD1', 'warehouse_code': 'WH1', 'quantity': 50},
        #     {'product_sku': 'PROD2', 'warehouse_code': 'WH2', 'quantity': 20},
        # ]
        #
        # Replace this with your actual old data source, e.g., CSV import or old field

        old_stock_data = self.get_old_stock_data()

        for record in old_stock_data:
            sku = record['product_sku']
            warehouse_code = record['warehouse_code']
            quantity = record['quantity']

            try:
                product = Product.objects.get(sku=sku)
            except Product.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Product with SKU {sku} does not exist. Skipping."))
                continue

            warehouse, created = Warehouse.objects.get_or_create(
                code=warehouse_code,
                defaults={'name': warehouse_code}
            )

            # Create or update stock
            stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=warehouse,
                defaults={'quantity': 0}
            )

            # Update quantity if needed
            if quantity > 0:
                stock.quantity = quantity
                stock.save()

                # Record a stock movement for reconciliation
                StockMovement.objects.create(
                    product=product,
                    warehouse=warehouse,
                    movement_type='IN',
                    quantity=quantity,
                    reference="Initial Stock Reconciliation",
                    source="Advanced Reconciliation Script"
                )

            self.stdout.write(f"{product.name} @ {warehouse.code}: set quantity = {stock.quantity}")

        self.stdout.write(self.style.SUCCESS("Advanced stock reconciliation completed!"))

    def get_old_stock_data(self):
        """
        Replace this method with how you read existing stock per warehouse.
        For example:
          - CSV import
          - Existing Product fields (quantity_on_hand + warehouse mapping)
          - External database
        Must return a list of dicts:
          [{'product_sku': 'PROD1', 'warehouse_code': 'WH1', 'quantity': 50}, ...]
        """
        # TEMPORARY EXAMPLE (replace with real data)
        return [
            {'product_sku': 'SKU-00001', 'warehouse_code': '001', 'quantity': 100},
            {'product_sku': 'SKU-00002', 'warehouse_code': '001', 'quantity': 50},
            {'product_sku': 'SKU-00003', 'warehouse_code': '001', 'quantity': 25},
            # Add more products
        ]
