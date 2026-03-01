from django.core.management.base import BaseCommand
from products.models import Product
from inventory.models import Warehouse, Stock, StockMovement

class Command(BaseCommand):
    help = "Reconcile existing inventory to Stock and StockMovement"

    def handle(self, *args, **options):
        # Example: For each product, add stock to default warehouse if missing
        default_warehouse, created = Warehouse.objects.get_or_create(
            code="DEFAULT",
            defaults={'name': "Default Warehouse"}
        )

        self.stdout.write("Reconciling stock for all products...")

        for product in Product.objects.all():
            # Check if a stock entry exists for this product in default warehouse
            stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=default_warehouse,
                defaults={'quantity': 0}
            )

            # If product has a quantity_on_hand value from old system, use it
            # Assuming old quantity_on_hand field exists temporarily
            try:
                old_qty = product.quantity_on_hand_old  # Replace with your actual old field
            except AttributeError:
                old_qty = 0

            if old_qty > 0:
                stock.quantity = old_qty
                stock.save()

                # Create a stock movement for record
                StockMovement.objects.create(
                    product=product,
                    warehouse=default_warehouse,
                    movement_type='IN',
                    quantity=old_qty,
                    reference="Initial Stock Reconciliation",
                    source="Reconciliation Script"
                )

            self.stdout.write(f"{product.name}: stock set to {stock.quantity}")

        self.stdout.write(self.style.SUCCESS("Inventory reconciliation completed!"))
