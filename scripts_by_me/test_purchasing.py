import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from purchasing.models import Vendor, PurchaseOrder, PurchaseOrderLine, PurchasingSettings
from inventory.models import Warehouse, Stock, StockBatch, StockMovement, InventorySettings
from products.models import Product, Unit, ProductCategory
from core.models import Country, City, Region
from decimal import Decimal

User = get_user_model()

class PurchasingIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')

        # Setup Core
        self.country = Country.objects.create(name='Test Country', code='TC', iso_code='TC')
        self.city = City.objects.create(name='Test City', country=self.country)

        # Setup Product
        self.category = ProductCategory.objects.create(name='Electronics')
        self.unit = Unit.objects.create(name='Piece', short_name='pc', code='PCS')
        self.product = Product.objects.create(
            name='Laptop',
            category=self.category,
            base_unit=self.unit,
            price=Decimal('1000.00'),
            cost=Decimal('800.00')
        )

        # Setup Warehouse
        self.warehouse = Warehouse.objects.create(name='Main Warehouse', code='WH001')

        # Setup Vendor
        self.vendor = Vendor.objects.create(
            name='Best Buy',
            code='BB001',
            email='sales@bestbuy.com',
            address_line1='123 Tech St',
            country=self.country,
            city=self.city,
            postal_code='12345'
        )

        # Ensure settings exist
        PurchasingSettings.get_settings()
        InventorySettings.get_settings()

    def test_purchase_order_lifecycle(self):
        # 1. Create Purchase Order
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            warehouse=self.warehouse,
            created_by=self.user
        )

        line = PurchaseOrderLine.objects.create(
            order=po,
            product=self.product,
            quantity=Decimal('10'),
            price=Decimal('800.00'),
            tax_rate=Decimal('10') # 10% tax
        )
        
        po.refresh_from_db()
        # Subtotal: 10 * 800 = 8000
        # Tax: 10% of 8000 = 800
        # Total: 8000 + 800 = 8800
        self.assertEqual(po.subtotal, Decimal('8000.00'))
        self.assertEqual(po.tax_amount, Decimal('800.00'))
        self.assertEqual(po.total_amount, Decimal('8800.00'))
        
        # 2. Confirm PO
        po.confirm()
        self.assertEqual(po.status, 'confirmed')
        
        # 3. Receive partial goods
        batch_info = {'batch_number': 'B001'}
        po.receive_line(line.id, Decimal('5'), batch_info=batch_info, user=self.user)

        line.refresh_from_db()
        po.refresh_from_db()
        self.assertEqual(line.received_quantity, Decimal('5'))
        self.assertEqual(po.status, 'partial')
        
        # 4. Check Stock and Movement
        stock = Stock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal('5'))
        
        movement = StockMovement.objects.filter(product=self.product, warehouse=self.warehouse).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, Decimal('5'))
        self.assertEqual(movement.movement_type, 'IN')
        
        # 5. Receive remaining goods
        batch_info = {'batch_number': 'B002'}
        po.receive_line(line.id, Decimal('5'), batch_info=batch_info, user=self.user)
        
        line.refresh_from_db()
        po.refresh_from_db()
        self.assertEqual(line.received_quantity, Decimal('10'))
        self.assertEqual(po.status, 'done')
        
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal('10'))

    def test_purchase_order_cancel(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            warehouse=self.warehouse,
            created_by=self.user
        )
        line = PurchaseOrderLine.objects.create(
            order=po,
            product=self.product,
            quantity=Decimal('10'),
            price=Decimal('800.00')
        )
        po.confirm()
        
        # Receive 3 units
        po.receive_line(line.id, Decimal('3'), user=self.user)
        
        stock = Stock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, Decimal('3'))
        
        # Cancel PO - should reverse stock
        po.cancel(user=self.user, reason="Ordered by mistake")
        
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal('0'))
        
        # Verify reversal movement
        reversal_movement = StockMovement.objects.filter(movement_type='OUT', source='return').first()
        self.assertIsNotNone(reversal_movement)
        self.assertEqual(reversal_movement.quantity, Decimal('3'))

if __name__ == "__main__":
    from django.test.utils import get_runner
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["scripts_by_me.test_purchasing"])
