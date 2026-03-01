# inventory/serializers.py
from rest_framework import serializers
from .models import Warehouse, WarehouseSection, Stock, StockMovement, StockCount, StockCountLine
from products.models import Product


class WarehouseSectionSerializer(serializers.ModelSerializer):
    """Serializer for WarehouseSection model"""
    full_location = serializers.ReadOnlyField()
    
    class Meta:
        model = WarehouseSection
        fields = '__all__'


class WarehouseSerializer(serializers.ModelSerializer):
    """Serializer for Warehouse model"""
    sections = WarehouseSectionSerializer(many=True, read_only=True)
    total_stock_value = serializers.SerializerMethodField()
    current_utilization = serializers.SerializerMethodField()
    available_capacity = serializers.SerializerMethodField()
    sections_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Warehouse
        fields = '__all__'
    
    def get_total_stock_value(self, obj):
        return float(obj.total_stock_value())
    
    def get_current_utilization(self, obj):
        return obj.current_utilization()
    
    def get_available_capacity(self, obj):
        capacity = obj.available_capacity()
        return float(capacity) if capacity is not None else None
    
    def get_sections_count(self, obj):
        return obj.sections.count()


class ProductBasicSerializer(serializers.ModelSerializer):
    """Basic Product serializer for nested relationships"""
    class Meta:
        model = Product
        fields = ['id', 'name', 'sku', 'code', 'product_type']


class StockSerializer(serializers.ModelSerializer):
    """Serializer for Stock model"""
    product_details = ProductBasicSerializer(source='product', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)
    section_location = serializers.SerializerMethodField()
    section_barcode = serializers.SerializerMethodField()
    unit_code = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    total_units_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Stock
        fields = '__all__'
    
    def get_section_location(self, obj):
        return obj.section.full_location if obj.section else None
    
    def get_section_barcode(self, obj):
        return obj.section.barcode if obj.section else None
    
    def get_unit_code(self, obj):
        if obj.unit:
            return getattr(obj.unit, 'code', getattr(obj.unit, 'short_name', 'unit'))
        return None
    
    def get_status(self, obj):
        if obj.is_frozen:
            return 'frozen'
        if obj.quantity <= 0:
            return 'out_of_stock'
        if obj.needs_reorder:
            return 'reorder'
        if obj.is_low_stock:
            return 'low_stock'
        if obj.is_overstocked:
            return 'overstocked'
        return 'ok'
    
    def get_total_units_display(self, obj):
        if obj.unit:
            unit_code = getattr(obj.unit, 'code', getattr(obj.unit, 'short_name', 'unit'))
            return f"{obj.total_units:.2f} {unit_code}"
        return f"{obj.quantity:.2f} base"


class StockMovementSerializer(serializers.ModelSerializer):
    """Serializer for StockMovement model"""
    product_details = ProductBasicSerializer(source='product', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)
    section_location = serializers.SerializerMethodField()
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    base_quantity = serializers.SerializerMethodField()
    net_effect = serializers.SerializerMethodField()
    
    class Meta:
        model = StockMovement
        fields = '__all__'
    
    def get_section_location(self, obj):
        return obj.section.full_location if obj.section else None
    
    def get_base_quantity(self, obj):
        return float(obj.base_quantity)
    
    def get_net_effect(self, obj):
        return float(obj.net_effect)


class StockAdjustmentSerializer(serializers.Serializer):
    """Serializer for stock adjustments"""
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    movement_type = serializers.ChoiceField(
        choices=['IN', 'OUT', 'ADJUSTMENT'],
        required=False,
        default='ADJUSTMENT'
    )
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero")
        return value


class StockTransferSerializer(serializers.Serializer):
    """Serializer for stock transfers between warehouses"""
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    source_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    target_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    section_from = serializers.PrimaryKeyRelatedField(
        queryset=WarehouseSection.objects.all(),
        required=False,
        allow_null=True
    )
    section_to = serializers.PrimaryKeyRelatedField(
        queryset=WarehouseSection.objects.all(),
        required=False,
        allow_null=True
    )
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Transfer quantity must be positive")
        return value
    
    def validate(self, data):
        if data['source_warehouse'] == data['target_warehouse']:
            raise serializers.ValidationError("Source and target warehouses must be different")
        
        # Check if source section belongs to source warehouse
        if data.get('section_from') and data['section_from'].warehouse != data['source_warehouse']:
            raise serializers.ValidationError("Source section must belong to source warehouse")
        
        # Check if target section belongs to target warehouse
        if data.get('section_to') and data['section_to'].warehouse != data['target_warehouse']:
            raise serializers.ValidationError("Target section must belong to target warehouse")
        
        return data


class StockCountLineSerializer(serializers.ModelSerializer):
    """Serializer for StockCountLine model"""
    product_details = ProductBasicSerializer(source='product', read_only=True)
    variance_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = StockCountLine
        fields = '__all__'
    
    def get_variance_percentage(self, obj):
        return float(obj.variance_percentage) if obj.variance_percentage else 0


class StockCountSerializer(serializers.ModelSerializer):
    """Serializer for StockCount model"""
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    section_location = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)
    lines = StockCountLineSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    total_variance = serializers.SerializerMethodField()
    
    class Meta:
        model = StockCount
        fields = '__all__'
    
    def get_section_location(self, obj):
        return obj.section.full_location if obj.section else None
    
    def get_items_count(self, obj):
        return obj.lines.count()
    
    def get_total_variance(self, obj):
        total = obj.lines.aggregate(total=serializers.model.Sum('variance'))['total'] or 0
        return float(total)


class DashboardSummarySerializer(serializers.Serializer):
    """Serializer for dashboard summary data"""
    total_warehouses = serializers.IntegerField()
    active_warehouses = serializers.IntegerField()
    total_stock_value = serializers.FloatField()
    total_products_in_stock = serializers.IntegerField()
    low_stock_items = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    recent_movements = StockMovementSerializer(many=True)
    warehouse_utilization = serializers.ListField(child=serializers.DictField())