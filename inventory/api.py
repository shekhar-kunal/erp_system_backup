# inventory/api.py
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Warehouse, Stock, StockMovement
from .serializers import (
    WarehouseSerializer, StockSerializer, StockMovementSerializer,
    StockTransferSerializer, StockAdjustmentSerializer
)
from .utils import InventoryManager


class WarehouseViewSet(viewsets.ModelViewSet):
    """API endpoint for warehouses"""
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['warehouse_type', 'is_active', 'temperature_zone']
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'created_at']
    
    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        """Get all stock in this warehouse"""
        warehouse = self.get_object()
        stock = Stock.objects.filter(warehouse=warehouse)
        serializer = StockSerializer(stock, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def utilization(self, request, pk=None):
        """Get warehouse utilization metrics"""
        warehouse = self.get_object()
        return Response({
            'name': warehouse.name,
            'capacity': float(warehouse.capacity) if warehouse.capacity else None,
            'current_utilization': warehouse.current_utilization(),
            'is_over_utilized': warehouse.is_over_utilized(),
            'available_capacity': float(warehouse.available_capacity()) if warehouse.available_capacity() else None,
            'total_stock_value': float(warehouse.total_stock_value()),
            'sections_count': warehouse.get_sections_count()
        })


class StockViewSet(viewsets.ModelViewSet):
    """API endpoint for stock"""
    queryset = Stock.objects.select_related('product', 'warehouse', 'section').all()
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['warehouse', 'product', 'section', 'is_frozen']
    search_fields = ['product__name', 'product__sku']
    ordering_fields = ['quantity', 'last_updated', 'reorder_level']
    
    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        """Adjust stock quantity"""
        stock = self.get_object()
        serializer = StockAdjustmentSerializer(data=request.data)
        
        if serializer.is_valid():
            qty = serializer.validated_data['quantity']
            movement_type = serializer.validated_data.get('movement_type', 'ADJUSTMENT')
            notes = serializer.validated_data.get('notes', '')
            
            try:
                if qty > 0:
                    movement = stock.add_stock(
                        qty=qty,
                        source='adjustment',
                        notes=notes,
                        user=request.user
                    )
                else:
                    movement = stock.remove_stock(
                        qty=abs(qty),
                        source='adjustment',
                        notes=notes,
                        user=request.user
                    )
                
                return Response({
                    'status': 'success',
                    'new_quantity': float(stock.quantity),
                    'movement_id': movement.id
                })
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Transfer stock between warehouses"""
        serializer = StockTransferSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                result = InventoryManager.transfer_stock(
                    product=serializer.validated_data['product'],
                    source_warehouse=serializer.validated_data['source_warehouse'],
                    target_warehouse=serializer.validated_data['target_warehouse'],
                    qty=serializer.validated_data['quantity'],
                    section_from=serializer.validated_data.get('section_from'),
                    section_to=serializer.validated_data.get('section_to'),
                    user=request.user,
                    reference=serializer.validated_data.get('reference', '')
                )
                
                return Response({
                    'status': 'success',
                    'source_movement_id': result['source_movement'].id,
                    'target_movement_id': result['target_movement'].id
                })
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get all low stock items"""
        stocks = Stock.objects.low_stock()
        page = self.paginate_queryset(stocks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(stocks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def valuation(self, request):
        """Get inventory valuation"""
        manager = InventoryManager()
        valuation = manager.get_inventory_valuation()
        return Response(valuation)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for stock movements (read-only)"""
    queryset = StockMovement.objects.select_related(
        'product', 'warehouse', 'section', 'created_by'
    ).all()
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['movement_type', 'source', 'warehouse', 'product']
    ordering_fields = ['created_at', 'quantity']
    ordering = ['-created_at']