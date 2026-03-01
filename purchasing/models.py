from django.db import models, transaction
from django.db.models import Sum, F, Q
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from products.models import Product, Unit
from inventory.models import Stock, Warehouse, WarehouseSection, StockBatch
from core.models import Country, City, Region


class Vendor(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True)
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True, help_text="Vendor website URL")
    
    # Address - Standardized format
    address_line1 = models.CharField(
        max_length=255,
        verbose_name="Address Line 1",
        help_text="Street address, P.O. box, company name"
    )
    address_line2 = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Address Line 2",
        help_text="Apartment, suite, unit, building, floor (optional)"
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name='vendor_countries',
        verbose_name="Country"
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name='vendor_regions',
        verbose_name="Region / State",
        null=True,
        blank=True
    )
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name='vendor_cities',
        verbose_name="City"
    )
    postal_code = models.CharField(
        max_length=20,
        verbose_name="ZIP / Postal Code",
        help_text="ZIP or postal code"
    )
    
    # Tax & Registration
    tax_number = models.CharField(max_length=100, blank=True, verbose_name="Tax ID/VAT Number")
    registration_number = models.CharField(max_length=100, blank=True, verbose_name="Company Registration Number")
    gst_number = models.CharField(max_length=50, blank=True, verbose_name="GST Number")
    
    # Financial
    payment_terms = models.CharField(
        max_length=50,
        choices=[
            ('immediate', 'Immediate'),
            ('net15', 'Net 15'),
            ('net30', 'Net 30'),
            ('net45', 'Net 45'),
            ('net60', 'Net 60'),
        ],
        default='net30'
    )
    credit_days = models.PositiveIntegerField(default=0, help_text="Credit days allowed")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD', choices=[
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('JPY', 'Japanese Yen'),
        ('CNY', 'Chinese Yuan'),
        ('INR', 'Indian Rupee'),
    ])
    
    # Vendor Performance
    average_delivery_days = models.PositiveIntegerField(default=0, editable=False)
    quality_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, editable=False)
    total_orders = models.PositiveIntegerField(default=0, editable=False)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_preferred = models.BooleanField(default=False, help_text="Mark as preferred vendor")
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendors_created'
    )

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower('code'),
                name='unique_vendor_code_case_insensitive'
            )
        ]
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['email']),
            models.Index(fields=['is_active', 'is_preferred']),
            models.Index(fields=['name']),
        ]
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"

    def clean(self):
        if Vendor.objects.filter(code__iexact=self.code).exclude(pk=self.pk).exists():
            raise ValidationError({'code': _("Vendor with this Code already exists.")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def full_address(self):
        """Return formatted full address"""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        if self.city:
            parts.append(self.city.name)
        if self.region:
            parts.append(self.region.name)
        if self.country:
            parts.append(self.country.name)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)

    @property
    def short_address(self):
        """Return short address (city, country)"""
        parts = []
        if self.city:
            parts.append(self.city.name)
        if self.country:
            parts.append(self.country.name)
        return ", ".join(parts)

    @property
    def total_purchases(self):
        """Calculate total purchases from this vendor"""
        total = self.purchaseorder_set.filter(
            status='done'
        ).aggregate(
            total=Sum('total_amount')
        )['total']
        return total or 0

    @property
    def outstanding_balance(self):
        """Calculate outstanding balance including opening balance and unpaid invoices"""
        # This would integrate with Accounts Payable module
        return self.opening_balance

    def update_performance_metrics(self):
        """Update vendor performance metrics based on completed orders"""
        completed_orders = self.purchaseorder_set.filter(status='done')
        self.total_orders = completed_orders.count()
        
        if self.total_orders > 0:
            # Calculate average delivery days
            delivery_days = []
            for order in completed_orders:
                if order.expected_date and order.receipts.exists():
                    actual_date = order.receipts.first().received_date.date()
                    delivery_days.append((actual_date - order.order_date).days)
            if delivery_days:
                self.average_delivery_days = sum(delivery_days) // len(delivery_days)
        
        self.save(update_fields=['average_delivery_days', 'total_orders'])


class PurchasingSettings(models.Model):
    """Feature toggles for Purchasing module"""
    enable_multi_currency = models.BooleanField(default=False)
    enable_purchase_approval = models.BooleanField(default=False)
    enable_batch_tracking = models.BooleanField(default=True)
    enable_quality_check = models.BooleanField(default=False)
    enable_partial_receiving = models.BooleanField(default=True)
    enable_auto_po_number = models.BooleanField(default=True)
    enable_vendor_credit_notes = models.BooleanField(default=False)
    enable_purchase_returns = models.BooleanField(default=False)
    enable_receipt_batching = models.BooleanField(default=False)
    
    # Approval workflow
    approval_levels = models.PositiveSmallIntegerField(
        default=1, 
        help_text="Number of approval levels required"
    )
    require_approval_above = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Require approval for orders above this amount"
    )
    
    # Default settings
    default_payment_terms = models.CharField(
        max_length=20, 
        default='net30',
        choices=[
            ('immediate', 'Immediate'),
            ('net15', 'Net 15'),
            ('net30', 'Net 30'),
            ('net45', 'Net 45'),
            ('net60', 'Net 60'),
        ]
    )
    default_warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # PO Numbering
    po_prefix = models.CharField(max_length=10, default='PO-')
    po_next_number = models.PositiveIntegerField(default=1)
    po_number_padding = models.PositiveIntegerField(default=4, help_text="Number of digits for PO number")
    
    # Notifications
    notify_on_overdue = models.BooleanField(default=True)
    notify_days_before = models.PositiveIntegerField(default=3)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = "Purchasing Settings"
        verbose_name_plural = "Purchasing Settings"
    
    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def save(self, *args, **kwargs):
        if not self.pk and PurchasingSettings.objects.exists():
            raise ValidationError("Only one PurchasingSettings instance can be created")
        super().save(*args, **kwargs)


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('confirmed', 'Confirmed'),      # order placed with vendor
        ('partial', 'Partially Received'),
        ('done', 'Done'),                 # fully received
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]

    PAYMENT_TERMS = [
        ('immediate', 'Immediate'),
        ('net15', 'Net 15'),
        ('net30', 'Net 30'),
        ('net45', 'Net 45'),
        ('net60', 'Net 60'),
        ('cod', 'Cash on Delivery'),
    ]

    po_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Leave blank to auto-generate"
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='purchase_orders')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    order_date = models.DateField(auto_now_add=True)
    expected_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Financial
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payment
    payment_terms = models.CharField(max_length=50, choices=PAYMENT_TERMS, default='net30')
    currency = models.CharField(max_length=3, default='USD')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=1.0)
    
    # Shipping
    shipping_address = models.TextField(blank=True, help_text="Leave blank to use vendor address")
    shipping_method = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    
    # Additional Info
    vendor_reference = models.CharField(max_length=100, blank=True, help_text="Vendor's PO number")
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='purchase_orders_created'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders_cancelled'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-order_date', '-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['vendor', 'order_date']),
            models.Index(fields=['po_number']),
            models.Index(fields=['expected_date']),
            models.Index(fields=['created_at']),
        ]
        permissions = [
            ("can_approve_purchase_orders", "Can approve purchase orders"),
            ("can_cancel_purchase_orders", "Can cancel purchase orders"),
        ]

    def __str__(self):
        return self.po_number

    def save(self, *args, **kwargs):
        settings = PurchasingSettings.get_settings()
        
        if not self.po_number and settings.enable_auto_po_number:
            self.po_number = self.generate_po_number()
        
        # Check if this is a new instance
        is_new = not self.pk
        
        # Save the instance first to get a primary key
        super().save(*args, **kwargs)
        
        # For new instances, calculate totals (lines might have been added after save)
        if is_new:
            self.calculate_totals()
            # Update only the total fields to avoid recursion
            super().save(update_fields=['subtotal', 'total_amount'])

    def generate_po_number(self):
        """Generate PO number based on settings"""
        settings = PurchasingSettings.get_settings()
        prefix = settings.po_prefix
        next_num = settings.po_next_number
        padding = settings.po_number_padding
        
        # Update next number
        settings.po_next_number = next_num + 1
        settings.save(update_fields=['po_next_number'])
        
        return f"{prefix}{str(next_num).zfill(padding)}"

    def calculate_totals(self):
        """Calculate order totals"""
        # Only calculate if we have a primary key
        if self.pk:
            aggregates = self.lines.aggregate(
                subtotal=Sum(F('quantity') * F('net_price')),
                tax_amount=Sum('tax_amount'),
                discount_amount=Sum(F('quantity') * F('discount_amount'))
            )
            
            self.subtotal = aggregates['subtotal'] or 0
            self.tax_amount = aggregates['tax_amount'] or 0
            self.discount_amount = aggregates['discount_amount'] or 0
            self.total_amount = self.subtotal + self.tax_amount + self.shipping_cost
        return self.total_amount

    @property
    def total_amount_display(self):
        """Return total with currency"""
        return f"{self.currency} {self.total_amount:,.2f}"

    @property
    def total_received(self):
        """Total quantity received across all lines"""
        return self.lines.aggregate(
            total=Sum('received_quantity')
        )['total'] or 0

    @property
    def is_fully_received(self):
        """Check if all items in this PO have been fully received"""
        if not self.pk or not self.lines.exists():
            return False
        return all(line.received_quantity == line.quantity for line in self.lines.all())

    @property
    def receipt_status(self):
        """Return receipt status as percentage"""
        if not self.lines.exists():
            return 0
        total_ordered = sum(line.quantity for line in self.lines.all())
        if total_ordered == 0:
            return 0
        return (self.total_received / total_ordered) * 100

    def confirm(self):
        """Change status from draft to confirmed – no stock impact."""
        if self.status not in ['draft', 'approved']:
            raise ValidationError("Only draft or approved orders can be confirmed.")
        self.status = 'confirmed'
        self.save()

    def approve(self, user):
        """Approve purchase order"""
        settings = PurchasingSettings.get_settings()
        
        if self.status != 'pending_approval':
            raise ValidationError("Only pending approval orders can be approved.")
        
        if self.total_amount > settings.require_approval_above:
            self.status = 'approved'
        else:
            self.status = 'confirmed'
        
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def get_receivable_lines(self):
        """
        Returns queryset of lines that can still receive quantities
        """
        return self.lines.filter(quantity__gt=F('received_quantity'))

    def can_receive(self, line_id, quantity):
        """
        Check if a specific quantity can be received for a line
        Returns (bool, message)
        """
        try:
            line = self.lines.get(id=line_id)
        except PurchaseOrderLine.DoesNotExist:
            return False, "Line not found"
        
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        remaining = line.remaining_quantity
        if quantity > remaining:
            return False, f"Cannot receive {quantity}, only {remaining} remaining"
        
        return True, "OK"

  
    @transaction.atomic
    def receive_line(self, line_id, quantity_to_receive, batch_info=None, quality_status='accepted', user=None):
        """
        Receive a partial quantity for a specific line.
        Updates stock and the line's received_quantity.
        Includes validation to prevent receiving more than ordered.
        """
        # Get the line
        line = self.lines.get(id=line_id)
        
        # STEP 1: Validate quantity is positive
        if quantity_to_receive <= 0:
            raise ValidationError(
                f"Quantity to receive must be positive. You entered: {quantity_to_receive}"
            )
        
        # STEP 2: Calculate maximum allowed quantity
        max_allowed = line.quantity - line.received_quantity
        
        # STEP 3: Validate not receiving more than remaining
        if quantity_to_receive > max_allowed:
            raise ValidationError(
                f"Cannot receive more than remaining quantity. "
                f"Ordered: {line.quantity}, "
                f"Already received: {line.received_quantity}, "
                f"Remaining: {max_allowed}, "
                f"Attempting to receive: {quantity_to_receive}"
            )
        
        # STEP 4: Check if line is already fully received
        if line.received_quantity >= line.quantity:
            raise ValidationError(
                f"This line is already fully received. "
                f"Ordered: {line.quantity}, Received: {line.received_quantity}"
            )

        settings = PurchasingSettings.get_settings()

        # Determine conversion factor to base unit
        # Since Unit doesn't have conversion_factor, use 1 as default
        unit_qty = 1

        warehouse = line.warehouse if line.warehouse else self.warehouse

        # Get or create stock record
        stock, _ = Stock.objects.get_or_create(
            product=line.product,
            warehouse=warehouse,
            section=line.section,
            defaults={
                'quantity': 0, 
                'unit_quantity': unit_qty,
                'unit': line.unit
            }
        )

        # Create stock batch if tracking enabled and batch info provided
        batch = None
        if settings.enable_batch_tracking and batch_info and batch_info.get('batch_number'):
            # Use stock.add_batch method which handles batch creation properly
            try:
                batch = stock.add_batch(
                    batch_number=batch_info['batch_number'],
                    quantity=quantity_to_receive,
                    expiry_date=batch_info.get('expiry_date'),
                    manufacturing_date=batch_info.get('manufacturing_date'),
                    supplier=self.vendor.name,
                    quality_status=quality_status,
                    reference=self.po_number,
                    source='purchase'
                )
            except Exception as e:
                # If add_batch fails, try direct creation
                from inventory.models import StockBatch
                batch, _ = StockBatch.objects.get_or_create(
                    stock=stock,
                    batch_number=batch_info['batch_number'],
                    defaults={
                        'expiry_date': batch_info.get('expiry_date'),
                        'manufacturing_date': batch_info.get('manufacturing_date'),
                        'supplier': self.vendor.name,
                        'quantity': quantity_to_receive,
                        'received_date': timezone.now().date(),
                        'quality_status': quality_status,
                        'is_active': True,
                        'unit': line.unit,
                        'unit_quantity': unit_qty
                    }
                )

        # Increase stock using the stock model's methods
        if settings.enable_batch_tracking and batch:
            # If using batch tracking, stock quantity is managed through batches
            # The batch creation already added to stock via stock.add_batch
            pass
        else:
            # Use the stock.add_stock method which handles movements properly
            stock.add_stock(
                qty=quantity_to_receive,
                reference=self.po_number,
                source="Purchase Receipt",
                unit_qty=unit_qty,
                notes=f"Received from PO {self.po_number}",
                user=user
            )

        # Update received quantity
        line.received_quantity += quantity_to_receive
        line.save()

        # Update order status based on receipt progress
        if all(l.received_quantity == l.quantity for l in self.lines.all()):
            self.status = 'done'
        elif any(l.received_quantity > 0 for l in self.lines.all()):
            self.status = 'partial'
        # else remains 'confirmed'
        
        self.save()
        
        return line, batch

    def update_status_from_receipts(self):
        """
        Update the order status based on receipt progress of all lines
        Use this when processing multiple receipts at once
        """
        if not self.pk:  # If order hasn't been saved yet
            return
            
        if all(line.received_quantity == line.quantity for line in self.lines.all()):
            if self.status != 'done':
                self.status = 'done'
                self.save(update_fields=['status'])
        elif any(line.received_quantity > 0 for line in self.lines.all()):
            if self.status != 'partial':
                self.status = 'partial'
                self.save(update_fields=['status'])
        # else remains current status

    @transaction.atomic
    def cancel(self, user=None, reason=""):
        """Cancel order and reverse any already received stock."""
        if self.status not in ['draft', 'confirmed', 'partial', 'approved']:
            raise ValidationError("Only active orders can be cancelled.")

        for line in self.lines.all():
            if line.received_quantity > 0:
                warehouse = line.warehouse if line.warehouse else self.warehouse
                try:
                    stock = Stock.objects.get(
                        product=line.product,
                        warehouse=warehouse,
                        section=line.section
                    )
                    stock.remove_stock(
                        qty=line.received_quantity,
                        reference=f"Cancel {self.po_number}",
                        source="return",
                        notes=f"Cancellation of PO {self.po_number}",
                        user=user
                    )
                except Stock.DoesNotExist:
                    pass
                line.received_quantity = 0
                line.save()

        self.status = 'cancelled'
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Unit in which this product is ordered. Leave blank for base unit."
    )

    # Discounts
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Location
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Optional: override order warehouse"
    )
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Optional: receive into specific bin"
    )
    
    # Receiving
    received_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Quantity already received into stock"
    )
    
    # Additional Info
    notes = models.CharField(max_length=255, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['order', 'product']),
        ]
        ordering = ['id']

    def __str__(self):
        if self.unit:
            unit_display = getattr(self.unit, 'code', getattr(self.unit, 'name', 'unit'))
            unit_str = f" ({unit_display})"
        else:
            unit_str = ""
        return f"{self.product.name if self.product else 'Unknown'} x {self.quantity}{unit_str}"

    def save(self, *args, **kwargs):
        # Ensure default values are set
        if self.quantity is None:
            self.quantity = 0
        if self.price is None:
            self.price = 0
        if self.discount_percent is None:
            self.discount_percent = 0
        if self.discount_amount is None:
            self.discount_amount = 0
        if self.tax_rate is None:
            self.tax_rate = 0
            
        self.calculate_totals()
        super().save(*args, **kwargs)
        # Update order totals
        if self.order_id:
            self.order.calculate_totals()
            self.order.save(update_fields=['subtotal', 'tax_amount', 'discount_amount', 'total_amount'])

    def calculate_totals(self):
        """Calculate line totals"""
        # Ensure we have valid numbers
        quantity = self.quantity or 0
        price = self.price or 0
        discount_percent = self.discount_percent or 0
        discount_amount = self.discount_amount or 0
        
        # Apply discount
        if discount_amount:
            self.net_price = price - discount_amount
        elif discount_percent:
            self.discount_amount = price * (discount_percent / 100)
            self.net_price = price - self.discount_amount
        else:
            self.net_price = price
        
        # Ensure net_price is not None
        if self.net_price is None:
            self.net_price = 0
        
        # Calculate tax
        if self.tax_rate:
            self.tax_amount = self.net_price * (self.tax_rate / 100) * quantity
        else:
            self.tax_amount = 0
        
        return {
            'subtotal': quantity * self.net_price,
            'tax': self.tax_amount,
            'total': (quantity * self.net_price) + self.tax_amount
        }

    @property
    def subtotal(self):
        """Calculate subtotal safely"""
        quantity = self.quantity or 0
        net_price = self.net_price or 0
        return quantity * net_price

    @property
    def remaining_quantity(self):
        quantity = self.quantity or 0
        received = self.received_quantity or 0
        return quantity - received

    @property
    def receipt_percentage(self):
        """Return receipt percentage for this line"""
        quantity = self.quantity or 0
        if quantity == 0:
            return 0
        received = self.received_quantity or 0
        return (received / quantity) * 100

    def clean(self):
        if self.received_quantity > self.quantity:
            raise ValidationError({
                'received_quantity': _('Received quantity cannot exceed ordered quantity.')
            })
        if self.discount_percent and self.discount_percent > 100:
            raise ValidationError({
                'discount_percent': _('Discount percentage cannot exceed 100%.')
            })


class PurchaseReceipt(models.Model):
    """Goods Receipt Note"""
    RECEIPT_STATUS = [
        ('draft', 'Draft'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    QUALITY_STATUS = [
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('quarantine', 'Quarantine'),
        ('partial', 'Partial Accept'),
    ]

    receipt_number = models.CharField(max_length=50, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder, 
        on_delete=models.PROTECT, 
        related_name='receipts'
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT
    )
    received_date = models.DateTimeField(auto_now_add=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    
    # Receipt Details
    delivery_note_number = models.CharField(max_length=100, blank=True, help_text="Vendor's delivery note number")
    vehicle_number = models.CharField(max_length=50, blank=True)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=50, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=RECEIPT_STATUS, default='draft')
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-received_date']
        indexes = [
            models.Index(fields=['receipt_number']),
            models.Index(fields=['purchase_order', 'status']),
            models.Index(fields=['received_date']),
        ]

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            last = PurchaseReceipt.objects.filter(
                receipt_number__startswith='GRN-'
            ).order_by('id').last()
            if last:
                try:
                    last_num = int(last.receipt_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            self.receipt_number = f"GRN-{last_num + 1:06d}"
        super().save(*args, **kwargs)


class PurchaseReceiptLine(models.Model):
    receipt = models.ForeignKey(
        PurchaseReceipt, 
        on_delete=models.CASCADE, 
        related_name='lines'
    )
    order_line = models.ForeignKey(
        PurchaseOrderLine, 
        on_delete=models.PROTECT,
        related_name='receipt_lines'
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_accepted = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_rejected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Quality
    quality_status = models.CharField(
        max_length=20, 
        choices=PurchaseReceipt.QUALITY_STATUS, 
        default='accepted'
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    
    # Batch tracking
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    manufacturing_date = models.DateField(null=True, blank=True)
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_receipt_lines'
    )
    
    # Location
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    notes = models.CharField(max_length=255, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['receipt', 'product']),
            models.Index(fields=['batch_number']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.quantity_received}"

    def save(self, *args, **kwargs):
        # Always recalculate accepted quantity if not provided or if being updated
        if self.quantity_accepted is None or 'quantity_rejected' in kwargs.get('update_fields', []) or not self.pk:
            self.quantity_accepted = (self.quantity_received or 0) - (self.quantity_rejected or 0)
        super().save(*args, **kwargs)


class PurchaseOrderHistory(models.Model):
    """Audit trail for purchase orders"""
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    action = models.CharField(max_length=50, choices=[
        ('create', 'Created'),
        ('update', 'Updated'),
        ('status_change', 'Status Changed'),
        ('approve', 'Approved'),
        ('cancel', 'Cancelled'),
        ('receive', 'Received'),
    ])
    
    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = "Purchase Order Histories"

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.action} at {self.changed_at}"