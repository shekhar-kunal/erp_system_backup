from django.db import transaction
from django.core.exceptions import ValidationError
from .models import (
    PurchaseOrder, PurchaseOrderLine, PurchasingSettings,
    PurchaseReceipt, PurchaseReceiptLine, StockBatch
)


class PurchaseOrderService:
    """Service layer for Purchase Order business logic"""
    
    def __init__(self, user=None):
        self.user = user
    
    @transaction.atomic
    def create_from_requisition(self, requisition, **kwargs):
        """Create PO from internal requisition"""
        po = PurchaseOrder.objects.create(
            vendor=requisition.vendor,
            warehouse=requisition.warehouse,
            expected_date=requisition.required_date,
            created_by=self.user,
            **kwargs
        )
        
        for item in requisition.items.all():
            PurchaseOrderLine.objects.create(
                order=po,
                product=item.product,
                quantity=item.quantity,
                price=item.product.cost_price,
                unit=item.unit
            )
        
        po.calculate_totals()
        return po
    
    @transaction.atomic
    def receive_goods(self, po, receipts_data):
        """Process multiple receipts for a PO"""
        receipt = PurchaseReceipt.objects.create(
            purchase_order=po,
            received_by=self.user,
            warehouse=po.warehouse
        )
        
        for line_data in receipts_data:
            line = po.lines.get(id=line_data['line_id'])
            
            if line_data['quantity'] > line.remaining_quantity:
                raise ValidationError(f"Cannot receive more than ordered for {line.product}")
            
            # Prepare batch info
            batch_info = {
                'batch_number': line_data.get('batch_number', ''),
                'expiry_date': line_data.get('expiry_date'),
                'manufacturing_date': line_data.get('manufacturing_date')
            }

            # Call receive_line which handles stock and batch creation
            updated_line, batch = po.receive_line(
                line.id,
                line_data['quantity'],
                batch_info=batch_info,
                user=self.user
            )

            # Create receipt line and link the created batch
            PurchaseReceiptLine.objects.create(
                receipt=receipt,
                order_line=line,
                product=line.product,
                quantity_received=line_data['quantity'],
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
                warehouse=line.warehouse or po.warehouse,
                batch=batch
            )
        
        receipt.status = 'completed'
        receipt.save()
        return receipt