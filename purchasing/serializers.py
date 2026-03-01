from rest_framework import serializers
from .models import (
    Vendor, PurchaseOrder, PurchaseOrderLine, 
    PurchaseReceipt, PurchaseReceiptLine, PurchasingSettings
)


class VendorSerializer(serializers.ModelSerializer):
    full_address = serializers.ReadOnlyField()
    short_address = serializers.ReadOnlyField()
    total_purchases = serializers.ReadOnlyField()
    
    class Meta:
        model = Vendor
        fields = [
            'id', 'name', 'code', 'contact_person', 'email', 'phone',
            'mobile', 'website', 'full_address', 'short_address',
            'address_line1', 'address_line2', 'country', 'region', 'city', 'postal_code',
            'tax_number', 'registration_number', 'gst_number',
            'payment_terms', 'credit_days', 'credit_limit',
            'opening_balance', 'currency', 'average_delivery_days',
            'quality_rating', 'total_orders', 'total_purchases',
            'is_active', 'is_preferred', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'average_delivery_days', 
                           'quality_rating', 'total_orders']


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_sku = serializers.SerializerMethodField()
    subtotal = serializers.ReadOnlyField()
    remaining_quantity = serializers.ReadOnlyField()
    receipt_percentage = serializers.ReadOnlyField()
    
    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'order', 'product', 'product_name', 'product_sku',
            'quantity', 'price', 'net_price', 'unit',
            'discount_percent', 'discount_amount',
            'tax_rate', 'tax_amount',
            'warehouse', 'section',
            'received_quantity', 'remaining_quantity',
            'subtotal', 'receipt_percentage', 'notes'
        ]
    
    def get_product_name(self, obj):
        return obj.product.name if obj.product else ""
    
    def get_product_sku(self, obj):
        return obj.product.sku if obj.product else ""


class PurchaseReceiptLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    order_line_id = serializers.ReadOnlyField(source='order_line.id')
    
    class Meta:
        model = PurchaseReceiptLine
        fields = [
            'id', 'receipt', 'order_line', 'order_line_id',
            'product', 'product_name',
            'quantity_received', 'quantity_accepted', 'quantity_rejected',
            'quality_status', 'rejection_reason',
            'batch_number', 'expiry_date', 'manufacturing_date',
            'warehouse', 'section', 'notes'
        ]
    
    def get_product_name(self, obj):
        return obj.product.name if obj.product else ""


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    lines = PurchaseReceiptLineSerializer(many=True, read_only=True)
    received_by_name = serializers.SerializerMethodField()
    po_number = serializers.ReadOnlyField(source='purchase_order.po_number')
    vendor_name = serializers.SerializerMethodField()
    
    class Meta:
        model = PurchaseReceipt
        fields = [
            'id', 'receipt_number', 'purchase_order', 'po_number', 'vendor_name',
            'received_by', 'received_by_name', 'received_date',
            'warehouse', 'delivery_note_number', 'vehicle_number',
            'driver_name', 'driver_phone', 'status', 'notes',
            'lines', 'created_at', 'updated_at'
        ]
        read_only_fields = ['receipt_number', 'received_date']
    
    def get_received_by_name(self, obj):
        if obj.received_by:
            return obj.received_by.get_full_name() or obj.received_by.username
        return ""
    
    def get_vendor_name(self, obj):
        return obj.purchase_order.vendor.name if obj.purchase_order else ""


class PurchaseOrderSerializer(serializers.ModelSerializer):
    vendor_name = serializers.ReadOnlyField(source='vendor.name')
    vendor_code = serializers.ReadOnlyField(source='vendor.code')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    total_amount_display = serializers.ReadOnlyField()
    receipt_status = serializers.ReadOnlyField()
    is_fully_received = serializers.ReadOnlyField()
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'vendor', 'vendor_name', 'vendor_code',
            'warehouse', 'warehouse_name', 'order_date', 'expected_date',
            'status', 'subtotal', 'tax_amount', 'shipping_cost',
            'discount_amount', 'total_amount', 'total_amount_display',
            'payment_terms', 'currency', 'exchange_rate',
            'shipping_address', 'shipping_method', 'tracking_number',
            'vendor_reference', 'notes', 'terms_conditions',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
            'approved_by', 'approved_by_name', 'approved_at',
            'cancelled_by', 'cancelled_by_name', 'cancelled_at', 'cancellation_reason',
            'receipt_status', 'is_fully_received'
        ]
        read_only_fields = ['po_number', 'created_at', 'updated_at']
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ""
    
    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return ""
    
    def get_cancelled_by_name(self, obj):
        if obj.cancelled_by:
            return obj.cancelled_by.get_full_name() or obj.cancelled_by.username
        return ""


class PurchaseOrderDetailSerializer(PurchaseOrderSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    receipts = PurchaseReceiptSerializer(many=True, read_only=True)
    
    class Meta(PurchaseOrderSerializer.Meta):
        fields = PurchaseOrderSerializer.Meta.fields + ['lines', 'receipts']


class PurchasingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchasingSettings
        fields = '__all__'