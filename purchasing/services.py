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
        settings = PurchasingSettings.get_settings()
        receipt = PurchaseReceipt.objects.create(
            purchase_order=po,
            received_by=self.user,
            warehouse=po.warehouse
        )
        
        for line_data in receipts_data:
            line = po.lines.get(id=line_data['line_id'])
            
            if line_data['quantity'] > line.remaining_quantity:
                raise ValidationError(f"Cannot receive more than ordered for {line.product}")
            
            # Create receipt line
            receipt_line = PurchaseReceiptLine.objects.create(
                receipt=receipt,
                order_line=line,
                product=line.product,
                quantity_received=line_data['quantity'],
                quantity_accepted=line_data['quantity'],
                batch_number=line_data.get('batch_number', ''),
                expiry_date=line_data.get('expiry_date'),
                warehouse=line.warehouse or po.warehouse
            )
            
            # Update stock with batch info if enabled
            if settings.enable_batch_tracking and line_data.get('batch_number'):
                # Create batch and link to stock movement
                batch = StockBatch.objects.create(
                    product=line.product,
                    batch_number=line_data['batch_number'],
                    expiry_date=line_data.get('expiry_date'),
                    manufacturing_date=line_data.get('manufacturing_date'),
                    supplier=po.vendor.name
                )
                receipt_line.batch = batch
                receipt_line.save()
                
            # Call existing receive_line method
            batch_info = {
                'batch_number': line_data.get('batch_number', ''),
                'expiry_date': line_data.get('expiry_date'),
                'manufacturing_date': line_data.get('manufacturing_date')
            }
            po.receive_line(line.id, line_data['quantity'], batch_info=batch_info)
        
        receipt.status = 'completed'
        receipt.save()
        return receipt