from django.db import models
from django.db.models import F, Q, Sum
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

User = get_user_model()

# inventory/models.py - Add this new model

class InventorySettings(models.Model):
    """Global inventory settings that can be toggled per client installation"""
    
    # Feature toggles
    enable_serial_tracking = models.BooleanField(
        default=False,
        help_text="Enable individual serial number tracking"
    )
    enable_batch_tracking = models.BooleanField(
        default=True,
        help_text="Enable batch/lot tracking with expiry dates"
    )
    enable_damaged_goods = models.BooleanField(
        default=False,
        help_text="Enable damaged goods recording"
    )
    enable_reservations = models.BooleanField(
        default=False,
        help_text="Enable stock reservations for sales orders"
    )
    enable_cycle_counting = models.BooleanField(
        default=False,
        help_text="Enable cycle counting workflow"
    )
    enable_auto_reorder = models.BooleanField(
        default=True,
        help_text="Enable automatic reorder alerts"
    )
    
    # Valuation method
    VALUATION_METHOD_CHOICES = [
        ('fifo', 'FIFO (First In First Out)'),
        ('lifo', 'LIFO (Last In First Out)'),
        ('average', 'Weighted Average'),
        ('standard', 'Standard Cost'),
    ]
    valuation_method = models.CharField(
        max_length=20,
        choices=VALUATION_METHOD_CHOICES,
        default='fifo',
        help_text="Default inventory valuation method"
    )
    
    # Reservation settings
    reservation_expiry_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours after which unfulfilled reservations auto-release"
    )
    allow_backorders = models.BooleanField(
        default=False,
        help_text="Allow backorders when stock is insufficient"
    )
    
    # Damaged goods settings
    require_writeoff_approval = models.BooleanField(
        default=True,
        help_text="Require manager approval for write-offs"
    )
    track_damage_reasons = models.BooleanField(
        default=True,
        help_text="Track reasons for damaged goods"
    )
    
    # Cycle counting settings
    cycle_count_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
        ],
        default='monthly'
    )
    cycle_count_by = models.CharField(
        max_length=20,
        choices=[
            ('section', 'By Section'),
            ('category', 'By Category'),
            ('value', 'By Value (ABC)'),
        ],
        default='section'
    )
    variance_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.0,
        help_text="Acceptable variance percentage before investigation"
    )
    
    # Single instance (only one settings record)
    class Meta:
        verbose_name_plural = "Inventory Settings"
    
    def __str__(self):
        return "Global Inventory Settings"
    
    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings


class WarehouseManager(models.Manager):
    def active(self):
        return self.filter(is_active=True)
    
    def main_warehouses(self):
        return self.filter(warehouse_type='main', is_active=True)
    
    def with_capacity_available(self):
        return self.annotate(
            current_stock=Sum('stock_entries__quantity')
        ).filter(
            current_stock__lt=F('capacity')
        )


class Warehouse(models.Model):
    WAREHOUSE_TYPE_CHOICES = [
        ('main', 'Main Warehouse'),
        ('branch', 'Branch'),
        ('cold_storage', 'Cold Storage'),
        ('third_party', 'Third Party'),
        ('dropship', 'Drop Shipping'),
        ('crossdock', 'Cross Dock'),
    ]

    TEMPERATURE_ZONE_CHOICES = [
        ('ambient', 'Ambient (15-25°C)'),
        ('cool', 'Cool (8-15°C)'),
        ('cold', 'Cold (2-8°C)'),
        ('frozen', 'Frozen (-18 to -25°C)'),
        ('hazardous', 'Hazardous Materials'),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    warehouse_type = models.CharField(
        max_length=20,
        choices=WAREHOUSE_TYPE_CHOICES,
        default='main'
    )
    temperature_zone = models.CharField(
        max_length=20,
        choices=TEMPERATURE_ZONE_CHOICES,
        default='ambient'
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses'
    )
    capacity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Optional capacity in base units"
    )
    capacity_unit = models.ForeignKey(
        'products.Unit',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='warehouse_capacities'
    )
    utilization_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=85.00,
        help_text="Alert when utilization exceeds this percentage"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    operating_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operating hours in JSON format"
    )
    meta_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WarehouseManager()

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Warehouses"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['warehouse_type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def total_stock_value(self):
        """Calculate total stock value in this warehouse"""
        return self.stock_entries.aggregate(
            total=Sum(models.F('quantity') * models.F('product__cost'))
        )['total'] or Decimal('0')

    def current_utilization(self):
        """Calculate current warehouse utilization percentage"""
        if not self.capacity or self.capacity <= 0:
            return 0
        total_stock = self.stock_entries.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        return (total_stock / self.capacity) * 100

    def is_over_utilized(self):
        """Check if warehouse is over utilized"""
        return self.current_utilization() > self.utilization_threshold

    def available_capacity(self):
        """Calculate available capacity"""
        if not self.capacity:
            return None
        total_stock = self.stock_entries.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        return self.capacity - total_stock

    def get_sections_count(self):
        return self.sections.count()


class WarehouseSectionManager(models.Manager):
    def active(self):
        return self.filter(is_active=True)
    
    def available(self):
        """Sections that have capacity available"""
        return self.filter(is_active=True).exclude(
            stock_entries__quantity__gte=F('max_capacity')
        )


class WarehouseSection(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    zone = models.CharField(max_length=20)
    aisle = models.CharField(max_length=20)
    rack = models.CharField(max_length=20)
    bin = models.CharField(max_length=20)
    
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)
    max_capacity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum capacity for this section"
    )
    current_occupancy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Current occupancy in base units"
    )
    
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WarehouseSectionManager()

    class Meta:
        unique_together = ('warehouse', 'zone', 'aisle', 'rack', 'bin')
        ordering = ['warehouse', 'zone', 'aisle', 'rack', 'bin']
        verbose_name_plural = "Warehouse Sections"
        indexes = [
            models.Index(fields=['warehouse', 'zone']),
            models.Index(fields=['barcode']),
        ]

    def __str__(self):
        return f"{self.warehouse.code} - {self.zone}-{self.aisle}-{self.rack}-{self.bin}"

    @property
    def full_location(self):
        return f"{self.zone}-{self.aisle}-{self.rack}-{self.bin}"

    @property
    def available_capacity(self):
        if self.max_capacity:
            return self.max_capacity - self.current_occupancy
        return None

    def update_occupancy(self):
        """Update current occupancy based on stock entries"""
        total = self.stock_entries.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        self.current_occupancy = total
        self.save(update_fields=['current_occupancy'])


class StockManager(models.Manager):
    def low_stock(self, threshold=None):
        """Get stock items below reorder level"""
        queryset = self.filter(quantity__lte=models.F('reorder_level'))
        if threshold:
            queryset = queryset.filter(quantity__lte=threshold)
        return queryset
    
    def out_of_stock(self):
        return self.filter(quantity__lte=0)
    
    def by_warehouse(self, warehouse):
        return self.filter(warehouse=warehouse)
    
    def fast_moving(self, days=30, min_movements=10):
        """Products with high movement in last N days"""
        cutoff_date = date.today() - timedelta(days=days)
        return self.annotate(
            movement_count=models.Count(
                'stock_movements',
                filter=models.Q(stock_movements__created_at__date__gte=cutoff_date)
            )
        ).filter(movement_count__gte=min_movements)
    
    def slow_moving(self, days=90):
        """Products with no movement in last N days"""
        cutoff_date = date.today() - timedelta(days=days)
        return self.annotate(
            last_movement=models.Max('stock_movements__created_at')
        ).filter(
            models.Q(last_movement__isnull=True) |
            models.Q(last_movement__date__lt=cutoff_date)
        )


class Stock(models.Model):
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='stock_entries'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stock_entries'
    )
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_entries'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Quantity on hand in base units"
    )
    unit = models.ForeignKey(
        'products.Unit',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    unit_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Number of base units per this unit"
    )
    
    # Stock level fields (moved from Product)
    reorder_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Alert when stock drops below this level"
    )
    max_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum desired stock level"
    )
    safety_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Safety stock level"
    )
    
    # NEW: Reserved quantity for sales orders
    reserved_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Quantity reserved for sales orders"
    )
    
    # Tracking fields
    last_counted = models.DateTimeField(null=True, blank=True)
    last_movement = models.DateTimeField(null=True, blank=True)
    is_frozen = models.BooleanField(default=False, help_text="Prevent stock movements")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StockManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'warehouse', 'section'],
                name='unique_product_warehouse_section'
            )
        ]
        indexes = [
            models.Index(fields=['product', 'warehouse']),
            models.Index(fields=['reorder_level']),
            models.Index(fields=['last_movement']),
            models.Index(fields=['is_frozen']),
        ]
        verbose_name_plural = "Stock"

    def __str__(self):
        location = f" @ {self.section}" if self.section else ""
        if self.unit:
            unit_code = getattr(self.unit, 'code', getattr(self.unit, 'short_name', 'unit'))
            unit_info = f" ({unit_code})"
        else:
            unit_info = ""
        return f"{self.product.name}{unit_info} - {self.warehouse.code}{location}"

    def clean(self):
        if self.quantity < 0:
            raise ValidationError({'quantity': _("Quantity cannot be negative.")})
        if self.unit_quantity <= 0:
            raise ValidationError({'unit_quantity': _("Unit quantity must be positive.")})
        if self.max_level and self.quantity > self.max_level:
            raise ValidationError(_("Quantity exceeds maximum level."))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ========== PROPERTIES FOR STOCK STATUS ==========

    @property
    def total_units(self):
        """Quantity in the selected unit"""
        return self.quantity / self.unit_quantity

    @property
    def base_quantity(self):
        """Quantity in base units (same as quantity field)"""
        return self.quantity

    @property
    def is_in_stock(self):
        """Check if stock is available"""
        return self.quantity > 0

    @property
    def needs_reorder(self):
        """Check if stock is below reorder level"""
        return self.quantity <= self.reorder_level

    @property
    def is_low_stock(self):
        """Check if stock is below safety stock"""
        return self.quantity <= self.safety_stock

    @property
    def is_overstocked(self):
        """Check if stock exceeds maximum level"""
        return self.max_level and self.quantity > self.max_level

    @property
    def total_value(self):
        """Calculate total value of this stock"""
        return self.quantity * (self.product.cost_price or 0)

    @property
    def available_quantity(self):
        """Quantity available for sale (considering reservations)"""
        from .models import InventorySettings
        settings = InventorySettings.get_settings()
        if settings.enable_reservations:
            return self.quantity - self.reserved_quantity
        return self.quantity

    # ========== STOCK MOVEMENT METHODS ==========

    def add_stock(self, qty, reference="", source="", unit_qty=None, notes="", user=None):
        """
        Add stock manually - creates a StockMovement record
        """
        if self.is_frozen:
            raise ValidationError(_("Cannot add stock to frozen item."))
        
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        
        if unit_qty is not None:
            if unit_qty <= 0:
                raise ValueError("Unit quantity must be positive")
            self.unit_quantity = unit_qty
        
        base_increase = qty * self.unit_quantity
        old_qty = self.quantity
        self.quantity += base_increase
        self.last_movement = timezone.now()
        self.save()
        
        movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            section=self.section,
            movement_type='IN',
            quantity=qty,
            unit_quantity=self.unit_quantity,
            reference=reference,
            source=source or "Manual Adjustment",
            notes=notes,
            created_by=user,
            previous_balance=old_qty,
            new_balance=self.quantity
        )
        
        if self.section:
            self.section.update_occupancy()
        
        return movement

    def remove_stock(self, qty, reference="", source="", notes="", user=None):
        """
        Remove stock manually - creates a StockMovement record
        """
        if self.is_frozen:
            raise ValidationError(_("Cannot remove stock from frozen item."))
        
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        
        required_base = qty * self.unit_quantity
        if self.quantity < required_base:
            raise ValueError(
                f"Insufficient stock. Available: {self.total_units} {self.unit.code if self.unit else 'units'} "
                f"({self.quantity} base), Requested: {qty}"
            )
        
        old_qty = self.quantity
        self.quantity -= required_base
        self.last_movement = timezone.now()
        self.save()
        
        movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            section=self.section,
            movement_type='OUT',
            quantity=qty,
            unit_quantity=self.unit_quantity,
            reference=reference,
            source=source or "Manual Adjustment",
            notes=notes,
            created_by=user,
            previous_balance=old_qty,
            new_balance=self.quantity
        )
        
        if self.section:
            self.section.update_occupancy()
        
        return movement

    def freeze(self):
        """Prevent any stock movements"""
        self.is_frozen = True
        self.save(update_fields=['is_frozen'])

    def unfreeze(self):
        """Allow stock movements"""
        self.is_frozen = False
        self.save(update_fields=['is_frozen'])

    # ========== RESERVATION METHODS (FEATURE TOGGLED) ==========

    def reserve(self, qty, order_ref, expiry_hours=None):
        """Reserve stock for a sales order"""
        from .models import InventorySettings, StockReservation
        
        settings = InventorySettings.get_settings()
        if not settings.enable_reservations:
            raise ValidationError("Stock reservations are not enabled")
        
        if qty <= 0:
            raise ValueError("Reservation quantity must be positive")
        
        if qty > self.available_quantity:
            if settings.allow_backorders:
                # Handle backorder
                return self.create_backorder(qty, order_ref)
            else:
                raise ValidationError(
                    f"Insufficient available stock. Available: {self.available_quantity}, Requested: {qty}"
                )
        
        self.reserved_quantity += qty
        self.save()
        
        # Create reservation record
        expiry = timezone.now() + timedelta(hours=expiry_hours or settings.reservation_expiry_hours)
        return StockReservation.objects.create(
            stock=self,
            quantity=qty,
            order_reference=order_ref,
            expires_at=expiry
        )

    def create_backorder(self, qty, order_ref):
        """Create backorder for insufficient stock"""
        from .models import InventorySettings, BackOrder
        
        settings = InventorySettings.get_settings()
        if not settings.allow_backorders:
            raise ValidationError("Backorders are not allowed")
        
        return BackOrder.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=qty,
            order_reference=order_ref,
            status='pending'
        )

    def release_reservation(self, reservation_id):
        """Release a specific reservation"""
        from .models import StockReservation
        
        try:
            reservation = StockReservation.objects.get(id=reservation_id, stock=self)
            reservation.release()
            return True
        except StockReservation.DoesNotExist:
            return False

    # ========== BATCH METHODS ==========

    def add_batch(self, batch_number, quantity, expiry_date=None, 
                  manufacturing_date=None, supplier="", **kwargs):
        """Add a new batch to this stock"""
        from .models import StockBatch, InventorySettings
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            raise ValidationError("Batch tracking is not enabled")
        
        batch = StockBatch.objects.create(
            stock=self,
            batch_number=batch_number,
            quantity=quantity,
            unit=self.unit,
            unit_quantity=self.unit_quantity,
            expiry_date=expiry_date,
            manufacturing_date=manufacturing_date,
            supplier=supplier,
            **kwargs
        )
        
        self.quantity += (quantity * self.unit_quantity)
        self.save()
        
        return batch

    def get_available_batches(self):
        """Get all active, non-expired batches ordered by expiry (FIFO)"""
        from datetime import date
        from .models import InventorySettings
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            return self.batches.none()
        
        return self.batches.filter(
            is_active=True,
            quantity__gt=0
        ).exclude(
            expiry_date__lt=date.today()
        ).order_by('expiry_date', 'received_date')

    def consume_fifo(self, qty, reference="", user=None):
        """Consume stock using FIFO (oldest batches first)"""
        from .models import InventorySettings
        
        settings = InventorySettings.get_settings()
        if not settings.enable_batch_tracking:
            # If batch tracking is disabled, just remove from stock directly
            self.remove_stock(qty, reference=reference, source="sale", user=user)
            return [{'batch': 'N/A', 'quantity': qty}]
        
        if qty > self.quantity:
            raise ValueError("Insufficient stock")
        
        batches = self.get_available_batches()
        remaining = qty
        movements = []
        
        for batch in batches:
            if remaining <= 0:
                break
            
            consume_qty = min(batch.quantity, remaining)
            batch.consume(consume_qty, reference, user)
            remaining -= consume_qty
            
            movements.append({
                'batch': batch.batch_number,
                'quantity': consume_qty
            })
        
        return movements


class StockMovementManager(models.Manager):
    def today(self):
        return self.filter(created_at__date=date.today())
    
    def this_week(self):
        return self.filter(created_at__week=date.today().isocalendar()[1])
    
    def this_month(self):
        return self.filter(created_at__month=date.today().month)
    
    def by_product(self, product):
        return self.filter(product=product)
    
    def by_warehouse(self, warehouse):
        return self.filter(warehouse=warehouse)


class StockMovement(models.Model):
    MOVEMENT_TYPE_CHOICES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('TRANSFER_IN', 'Transfer In'),
        ('TRANSFER_OUT', 'Transfer Out'),
        ('ADJUSTMENT', 'Adjustment'),
        ('RETURN', 'Return'),
        ('DAMAGE', 'Damage/Written Off'),
        ('COUNT', 'Stock Count'),
    ]
    
    SOURCE_CHOICES = [
        ('purchase', 'Purchase Receipt'),
        ('sale', 'Sales Issue'),
        ('transfer', 'Warehouse Transfer'),
        ('adjustment', 'Manual Adjustment'),
        ('return', 'Return'),
        ('damage', 'Damage/Written Off'),
        ('count', 'Stock Count'),
        ('production', 'Production'),
        ('assembly', 'Assembly'),
    ]

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='stock_movements'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stock_movements'
    )
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements'
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='adjustment')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    previous_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True, null=True, help_text="Reference document (PO, SO, etc.)")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_stock_movements'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StockMovementManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', 'warehouse']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['reference']),
            models.Index(fields=['source']),
            models.Index(fields=['movement_type']),
        ]
        verbose_name_plural = "Stock Movements"

    def __str__(self):
        return f"{self.get_movement_type_display()} | {self.product.name} | {self.quantity} x {self.unit_quantity} @ {self.warehouse.code}"

    @property
    def base_quantity(self):
        return self.quantity * self.unit_quantity

    @property
    def display_quantity(self):
        unit_code = self.product.unit.code if self.product.unit else 'base'
        return f"{self.quantity} {unit_code} (={self.base_quantity} base)"

    @property
    def net_effect(self):
        if self.movement_type in ['IN', 'TRANSFER_IN', 'RETURN']:
            return self.base_quantity
        else:
            return -self.base_quantity

    def save(self, *args, **kwargs):
        if not self.source:
            self.source = 'adjustment'
        super().save(*args, **kwargs)


class StockBatch(models.Model):
    """Track batches/lots of products for expiry and traceability"""
    
    QUALITY_STATUS_CHOICES = [
        ('pending', 'Pending Inspection'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('quarantine', 'In Quarantine'),
    ]

    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        related_name='batches'
    )
    batch_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique batch/lot number"
    )
    manufacturing_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of manufacture"
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of expiry"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Quantity in this batch"
    )
    unit = models.ForeignKey(
        'products.Unit',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    unit_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Number of base units per this unit"
    )
    received_date = models.DateField(
        auto_now_add=True,
        help_text="Date batch was received"
    )
    supplier = models.CharField(
        max_length=100,
        blank=True,
        help_text="Supplier/vendor name"
    )
    supplier_batch = models.CharField(
        max_length=50,
        blank=True,
        help_text="Supplier's batch number"
    )
    quality_status = models.CharField(
        max_length=20,
        choices=QUALITY_STATUS_CHOICES,
        default='pending'
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expiry_date', 'batch_number']
        indexes = [
            models.Index(fields=['batch_number']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['quality_status']),
        ]

    def __str__(self):
        return f"{self.batch_number} - {self.stock.product.name} ({self.quantity})"

    @property
    def is_expired(self):
        from datetime import date
        if self.expiry_date:
            return self.expiry_date < date.today()
        return False

    @property
    def days_to_expiry(self):
        from datetime import date
        if self.expiry_date:
            delta = self.expiry_date - date.today()
            return delta.days
        return None

    @property
    def total_base_quantity(self):
        return self.quantity * self.unit_quantity

    def consume(self, qty, reference="", user=None):
        """Remove quantity from batch (FIFO consumption)"""
        if qty > self.quantity:
            raise ValueError(f"Insufficient quantity in batch {self.batch_number}")
        
        self.quantity -= qty
        self.save()
        
        self.stock.quantity -= (qty * self.unit_quantity)
        self.stock.save()
        
        return True


class StockCount(models.Model):
    """Physical stock count records"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stock_counts'
    )
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_counts'
    )
    name = models.CharField(max_length=100)
    count_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_stock_counts'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='approved_stock_counts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Add cycle counting specific fields
    COUNT_TYPE_CHOICES = [
        ('full', 'Full Physical Inventory'),
        ('cycle', 'Cycle Count'),
        ('spot', 'Spot Check'),
    ]
    count_type = models.CharField(max_length=20, choices=COUNT_TYPE_CHOICES, default='full')
    
    cycle_category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Category/section being cycle counted"
    )
    
    scheduled_date = models.DateField(null=True, blank=True)
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_counts'
    )
    
    variance_approved = models.BooleanField(default=False)
    variance_approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_variances'
    )
    variance_approval_date = models.DateTimeField(null=True, blank=True)
    
    def auto_schedule_cycle_counts(self):
        """Automatically schedule cycle counts based on settings"""
        settings = InventorySettings.get_settings()
        if not settings.enable_cycle_counting:
            return
        
        # Implementation for automatic cycle counting
        pass

    class Meta:
        ordering = ['-count_date', '-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['count_date']),
        ]

    def __str__(self):
        return f"{self.name} - {self.warehouse.name} ({self.count_date})"


class StockCountLine(models.Model):
    """Individual line items in a stock count"""
    stock_count = models.ForeignKey(
        StockCount,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE
    )
    expected_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    counted_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('stock_count', 'product')

    def save(self, *args, **kwargs):
        if self.counted_quantity is not None:
            self.variance = self.counted_quantity - self.expected_quantity
        super().save(*args, **kwargs)

    @property
    def variance_percentage(self):
        if self.expected_quantity:
            return (self.variance / self.expected_quantity) * 100
        return 0
    
# inventory/models.py - Add this model

class SerialNumber(models.Model):
    """Individual serial number tracking for high-value items"""
    
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='serial_numbers'
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='serial_numbers'
    )
    serial_number = models.CharField(max_length=100, unique=True)
    
    STATUS_CHOICES = [
        ('in_stock', 'In Stock'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
        ('returned', 'Returned'),
        ('damaged', 'Damaged'),
        ('warranty', 'Under Warranty'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock')
    
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='serial_numbers'
    )
    section = models.ForeignKey(
        WarehouseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    manufacturing_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    sold_date = models.DateField(null=True, blank=True)
    sold_to = models.CharField(max_length=200, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['serial_number']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - SN: {self.serial_number}"
    
    @classmethod
    def is_enabled(cls):
        """Check if serial tracking is enabled"""
        return InventorySettings.get_settings().enable_serial_tracking    
    
# inventory/models.py - Add this model

class DamagedGoods(models.Model):
    """Track damaged inventory for insurance and write-offs"""
    
    DAMAGE_TYPE_CHOICES = [
        ('shipping', 'Shipping Damage'),
        ('handling', 'Handling Damage'),
        ('storage', 'Storage Damage'),
        ('expired', 'Expired'),
        ('defective', 'Manufacturing Defect'),
        ('other', 'Other'),
    ]
    
    DISPOSITION_CHOICES = [
        ('write_off', 'Write Off'),
        ('return_to_supplier', 'Return to Supplier'),
        ('sell_as_scrap', 'Sell as Scrap'),  # ← Fixed: added parentheses
        ('donate', 'Donate'),
        ('repair', 'Repair'),
    ]
    
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        related_name='damaged_items'
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='damaged_items'
    )
    serial_number = models.ForeignKey(
        SerialNumber,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    damage_type = models.CharField(max_length=20, choices=DAMAGE_TYPE_CHOICES)
    disposition = models.CharField(max_length=20, choices=DISPOSITION_CHOICES)
    
    description = models.TextField()
    reported_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reported_damages'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_damages'
    )
    
    insurance_claim = models.BooleanField(default=False)
    claim_number = models.CharField(max_length=100, blank=True)
    claim_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    is_approved = models.BooleanField(default=False)
    approval_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Damaged Goods"
        indexes = [
            models.Index(fields=['damage_type']),
            models.Index(fields=['is_approved']),
        ]
    
    def __str__(self):
        return f"{self.stock.product.name} - {self.quantity} units - {self.damage_type}"
    
    def approve(self, user):
        """Approve damage write-off"""
        from .models import InventorySettings
        
        settings = InventorySettings.get_settings()
        if settings.require_writeoff_approval and not user.has_perm('inventory.can_approve_writeoff'):
            raise ValidationError("User does not have permission to approve write-offs")
        
        self.is_approved = True
        self.approved_by = user
        self.approval_date = timezone.now()
        self.save()
        
        # Remove from stock
        self.stock.remove_stock(
            qty=self.quantity,
            source='damage',
            reference=f"Damage #{self.id}",
            notes=f"Damaged goods write-off: {self.description}",
            user=user
        )

# inventory/models.py - Add this model

class StockReservation(models.Model):
    """Reserve stock for sales orders"""
    
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    order_reference = models.CharField(max_length=100, help_text="Sales Order #")
    order_line_id = models.PositiveIntegerField(null=True, blank=True)
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('fulfilled', 'Fulfilled'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['order_reference']),
            models.Index(fields=['status', 'expires_at']),
        ]
    
    def __str__(self):
        return f"Reservation for {self.order_reference}: {self.quantity} units"
    
    def fulfill(self):
        """Convert reservation to actual sale"""
        self.status = 'fulfilled'
        self.fulfilled_at = timezone.now()
        self.save()
        
        # Reduce stock and reserved quantity
        self.stock.reserved_quantity -= self.quantity
        self.stock.quantity -= self.quantity
        self.stock.save()
    
    def release(self):
        """Release reservation (expired or cancelled)"""
        self.status = 'expired' if self.is_expired else 'cancelled'
        self.save()
        
        self.stock.reserved_quantity -= self.quantity
        self.stock.save()
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

# inventory/models.py - Add this model

class BackOrder(models.Model):
    """Track items on backorder"""
    
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='backorders'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    order_reference = models.CharField(max_length=100)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partially_fulfilled', 'Partially Fulfilled'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    quantity_fulfilled = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['order_reference']),
        ]
    
    def __str__(self):
        return f"Backorder {self.order_reference}: {self.product.name} - {self.quantity}"
    
    @property
    def remaining(self):
        return self.quantity - self.quantity_fulfilled
    
    def fulfill(self, qty):
        """Partially or fully fulfill backorder"""
        if qty > self.remaining:
            raise ValidationError(f"Cannot fulfill more than remaining quantity ({self.remaining})")
        
        self.quantity_fulfilled += qty
        if self.quantity_fulfilled >= self.quantity:
            self.status = 'fulfilled'
        else:
            self.status = 'partially_fulfilled'
        self.save()    
