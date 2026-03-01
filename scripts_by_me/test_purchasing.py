#!/usr/bin/env python
"""
Test script for Purchasing module
Run with: python test_purchasing.py
"""

import os
import django
import sys
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from purchasing.models import Vendor, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine
from products.models import Product, Unit
from inventory.models import Warehouse, Stock
from core.models import Country, City, Region

User = get_user_model()


def create_test_data():
    """Create all necessary test data"""
    print("\n1. Creating test data...")
    
    # Get or create a user for received_by
    try:
        user = User.objects.filter(is_staff=True).first()
        if not user:
            user = User.objects.create_user(
                username='testuser',
                password='testpass123',
                is_staff=True,
                is_superuser=True
            )
        print(f"   ✓ Using user: {user.username}")
    except Exception as e:
        print(f"   ⚠ Could not create user: {e}")
        user = None
    
    # Get or create Country
    try:
        country = Country.objects.get(code="US")
        print(f"   ✓ Using country: {country.name}")
    except Country.DoesNotExist:
        country = Country.objects.first()
        if country:
            print(f"   ✓ Using first available country: {country.name}")
        else:
            print("   ⚠ No country found. Please run setup_test_data.py first")
            return None
    
    # Get or create Region
    try:
        region = Region.objects.get(name="New York", country=country)
    except Region.DoesNotExist:
        region = Region.objects.filter(country=country).first()
    
    # Get or create City
    try:
        city = City.objects.get(name="New York City", country=country)
    except City.DoesNotExist:
        city = City.objects.filter(country=country).first()
    
    # Create Vendor
    vendor_data = {
        'name': "Test Vendor",
        'code': "TEST001",
        'contact_person': "John Doe",
        'email': "test@vendor.com",
        'phone': "+1234567890",
        'mobile': "+1987654321",
        'website': "https://testvendor.com",
        'address_line1': "123 Business Ave",
        'address_line2': "Suite 100",
        'country': country,
        'postal_code': "10001",
        'payment_terms': 'net30',
        'credit_days': 30,
        'credit_limit': 10000.00,
        'opening_balance': 0.00,
        'currency': 'USD',
        'is_active': True,
        'is_preferred': True
    }
    
    # Add optional fields if they exist
    if region:
        vendor_data['region'] = region
    if city:
        vendor_data['city'] = city
    
    vendor, created = Vendor.objects.get_or_create(
        code="TEST001",
        defaults=vendor_data
    )
    
    if created:
        print(f"   ✓ Vendor created: {vendor.name}")
    else:
        print(f"   ✓ Using existing vendor: {vendor.name}")
    
    # Get Warehouse
    warehouse = Warehouse.objects.filter(is_active=True).first()
    if warehouse:
        print(f"   ✓ Using warehouse: {warehouse.name}")
    else:
        print("   ⚠ No warehouse found. Please run setup_test_data.py first")
        return None
    
    # Get Unit
    unit = Unit.objects.filter(is_active=True).first()
    if unit:
        print(f"   ✓ Using unit: {unit.name}")
    else:
        print("   ⚠ No unit found. Please run setup_test_data.py first")
        return None
    
    return {
        'country': country,
        'region': region,
        'city': city,
        'vendor': vendor,
        'warehouse': warehouse,
        'unit': unit,
        'user': user
    }


def test_purchase_order_workflow(data):
    """Test complete purchase order workflow"""
    print("\n2. Testing Purchase Order Workflow...")
    
    # Check for products
    products = Product.objects.filter(active=True)[:2]
    if not products:
        print("   ⚠ No products found. Please run setup_test_data.py first")
        return None
    
    print(f"   Found {products.count()} products")
    
    # Create Purchase Order
    po = PurchaseOrder.objects.create(
        vendor=data['vendor'],
        warehouse=data['warehouse'],
        expected_date=datetime.now().date() + timedelta(days=7),
        payment_terms='net30',
        currency='USD',
        shipping_address=data['vendor'].full_address,
        notes="Test purchase order"
    )
    print(f"   ✓ PO created: {po.po_number}")
    
    # Add line items
    for i, product in enumerate(products):
        line = PurchaseOrderLine.objects.create(
            order=po,
            product=product,
            quantity=10 * (i + 1),
            price=100.00,
            unit=data['unit'],
            discount_percent=5 if i == 1 else 0,
            tax_rate=10
        )
        print(f"   ✓ Added: {product.name} x {line.quantity} @ ${line.price}")
    
    # Update totals
    po.calculate_totals()
    po.save(update_fields=['subtotal', 'total_amount'])
    print(f"   PO Total: ${po.total_amount}")
    
    return po


def test_confirmation(po):
    """Test PO confirmation"""
    print("\n3. Testing Confirmation...")
    
    if po.status != 'draft':
        print(f"   ⚠ PO already has status: {po.get_status_display()}")
        return
    
    try:
        po.confirm()
        print(f"   ✓ PO confirmed. Status: {po.get_status_display()}")
    except Exception as e:
        print(f"   ✗ Confirmation failed: {e}")


def test_partial_receive(po, data):
    """Test partial receiving using receive_line method"""
    print("\n4. Testing Partial Receive using receive_line...")
    
    if po.status not in ['confirmed', 'partial']:
        print(f"   ⚠ Cannot receive - PO status: {po.get_status_display()}")
        return None
    
    if not data['user']:
        print("   ⚠ No user available")
        return None
    
    try:
        # Receive half of each line using receive_line method
        for line in po.lines.all():
            receive_qty = line.quantity / 2  # Receive half
            po.receive_line(
                line.id, 
                receive_qty,
                batch_info={'batch_number': f'BATCH{line.id}001'}
            )
            print(f"   ✓ Received {receive_qty} of {line.product.name} via receive_line")
            print(f"     Remaining: {line.remaining_quantity}")
        
        po.refresh_from_db()
        print(f"   PO Status after partial receive: {po.get_status_display()}")
        print(f"   Receipt progress: {po.receipt_status:.1f}%")
        print(f"   Fully received: {po.is_fully_received}")
        
    except Exception as e:
        print(f"   ✗ Failed to receive: {e}")
        import traceback
        traceback.print_exc()


def test_complete_receive(po, data):
    """Test completing the receive using receive_line method"""
    print("\n5. Testing Complete Receive using receive_line...")
    
    if po.status not in ['confirmed', 'partial']:
        print(f"   ⚠ Cannot receive - PO status: {po.get_status_display()}")
        return
    
    try:
        # Receive remaining quantities using receive_line method
        for line in po.lines.all():
            if line.remaining_quantity > 0:
                receive_qty = line.remaining_quantity
                po.receive_line(
                    line.id, 
                    receive_qty,
                    batch_info={'batch_number': f'BATCH{line.id}002'}
                )
                print(f"   ✓ Received remaining {receive_qty} of {line.product.name} via receive_line")
        
        po.refresh_from_db()
        print(f"   Final PO Status: {po.get_status_display()}")
        print(f"   Fully received: {po.is_fully_received}")
        
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        import traceback
        traceback.print_exc()


def test_receipt_workflow(po, data):
    """Alternative test using PurchaseReceipt model (for completeness)"""
    print("\n4b. Testing Receipt Workflow (Alternative Method)...")
    
    if po.status not in ['confirmed', 'partial']:
        print(f"   ⚠ Cannot receive - PO status: {po.get_status_display()}")
        return None
    
    if not data['user']:
        print("   ⚠ No user available for received_by")
        return None
    
    try:
        # Create a receipt
        receipt = PurchaseReceipt.objects.create(
            purchase_order=po,
            received_by=data['user'],
            warehouse=data['warehouse'],
            status='draft',
            notes="Test receipt"
        )
        print(f"   ✓ Receipt created: {receipt.receipt_number}")
        
        # Receive items using receipt lines
        for line in po.lines.all():
            receive_qty = line.quantity / 2  # Receive half
            
            receipt_line = PurchaseReceiptLine.objects.create(
                receipt=receipt,
                order_line=line,
                product=line.product,
                quantity_received=receive_qty,
                quantity_accepted=receive_qty,
                quality_status='accepted',
                warehouse=data['warehouse']
            )
            print(f"   ✓ Added receipt line for {receive_qty} of {line.product.name}")
            
            # IMPORTANT: Call receive_line to update the order
            po.receive_line(
                line.id, 
                receive_qty,
                batch_info={'batch_number': f'BATCH{line.id}001'}
            )
        
        # Complete the receipt
        receipt.status = 'completed'
        receipt.save()
        print(f"   ✓ Receipt completed")
        
        po.refresh_from_db()
        print(f"   PO Status after receipt: {po.get_status_display()}")
        print(f"   Receipt progress: {po.receipt_status:.1f}%")
        
        return receipt
        
    except Exception as e:
        print(f"   ✗ Receiving failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_validation(po, data):
    """Test validation (should fail)"""
    print("\n6. Testing Validation (Should Fail)...")
    
    try:
        # Try to receive more on a completed order
        if po.status == 'done':
            line = po.lines.first()
            po.receive_line(line.id, 1)
            print("   ✗ Validation failed - should not allow receiving on completed PO")
        else:
            print(f"   ⚠ PO not in 'done' status for validation test (current: {po.status})")
            print(f"   Expected: done, but got: {po.status}")
            
    except Exception as e:
        print(f"   ✓ Validation working correctly: {e}")


def test_cancellation(data):
    """Test order cancellation"""
    print("\n7. Testing Cancellation...")
    
    products = Product.objects.filter(active=True)[:1]
    if not products:
        print("   ⚠ No products found")
        return
    
    # Create a new PO for cancellation test
    po = PurchaseOrder.objects.create(
        vendor=data['vendor'],
        warehouse=data['warehouse'],
        expected_date=datetime.now().date() + timedelta(days=14),
        notes="Test cancellation"
    )
    
    # Add a line
    line = PurchaseOrderLine.objects.create(
        order=po,
        product=products[0],
        quantity=5,
        price=50.00,
        unit=data['unit']
    )
    print(f"   ✓ Created PO: {po.po_number}")
    
    # Update totals
    po.calculate_totals()
    po.save(update_fields=['subtotal', 'total_amount'])
    
    # Cancel the PO
    try:
        po.status = 'cancelled'
        po.cancellation_reason = "Testing cancellation workflow"
        po.save()
        print(f"   ✓ PO cancelled. Status: {po.get_status_display()}")
    except Exception as e:
        print(f"   ✗ Cancellation failed: {e}")


def run_tests():
    """Main test function"""
    print("=" * 60)
    print("TESTING PURCHASING MODULE")
    print("=" * 60)
    
    try:
        # Step 1: Create test data
        data = create_test_data()
        
        if not data:
            print("\n❌ Test data creation failed. Please run setup_test_data.py first.")
            return
        
        # Step 2: Test PO workflow
        po = test_purchase_order_workflow(data)
        
        if po:
            # Step 3: Test confirmation
            test_confirmation(po)
            
            # Step 4: Test partial receive using receive_line
            test_partial_receive(po, data)
            
            # Step 5: Test complete receive using receive_line
            test_complete_receive(po, data)
            
            # Step 6: Test validation
            test_validation(po, data)
        
        # Step 7: Test cancellation
        test_cancellation(data)
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS COMPLETED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_tests()