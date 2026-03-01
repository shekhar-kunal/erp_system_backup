# purchasing/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Vendor, PurchaseOrder, PurchaseOrderLine
from .services import PurchaseOrderService

User = get_user_model()

class PurchaseOrderTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.vendor = Vendor.objects.create(
            name='Test Vendor',
            code='TV001',
            email='vendor@test.com'
        )
    
    def test_create_purchase_order(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            warehouse_id=1,
            created_by=self.user
        )
        self.assertEqual(po.status, 'draft')
        self.assertTrue(po.po_number.startswith('PO-'))
    
    def test_receive_goods(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            warehouse_id=1
        )
        line = PurchaseOrderLine.objects.create(
            order=po,
            product_id=1,
            quantity=10,
            price=100
        )
        
        service = PurchaseOrderService(user=self.user)
        po.confirm()
        
        # Receive 5 units
        po.receive_line(line.id, 5)
        
        line.refresh_from_db()
        self.assertEqual(line.received_quantity, 5)
        self.assertEqual(po.status, 'partial')