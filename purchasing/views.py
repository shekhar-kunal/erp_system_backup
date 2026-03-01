from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Vendor, PurchaseOrder, PurchaseReceipt, PurchaseOrderLine
from .serializers import (
    VendorSerializer, PurchaseOrderSerializer, PurchaseReceiptSerializer,
    PurchaseOrderDetailSerializer, PurchaseOrderLineSerializer
)
from .dashboard import PurchasingDashboard
from .services import PurchaseOrderService


# ===================== API ViewSets =====================

class VendorViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing vendors
    """
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Vendor.objects.all()
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by preferred status
        is_preferred = self.request.query_params.get('is_preferred', None)
        if is_preferred is not None:
            queryset = queryset.filter(is_preferred=is_preferred.lower() == 'true')
        
        # Search by name or code
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search) |
                Q(email__icontains=search)
            )
        
        return queryset
    
    @action(detail=True, methods=['get'])
    def purchase_orders(self, request, pk=None):
        """Get all purchase orders for a vendor"""
        vendor = self.get_object()
        orders = vendor.purchase_orders.all()
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = PurchaseOrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PurchaseOrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get vendor performance metrics"""
        vendor = self.get_object()
        vendor.update_performance_metrics()
        
        data = {
            'vendor_id': vendor.id,
            'vendor_name': vendor.name,
            'total_orders': vendor.total_orders,
            'average_delivery_days': vendor.average_delivery_days,
            'quality_rating': float(vendor.quality_rating),
            'total_purchases': float(vendor.total_purchases),
            'outstanding_balance': float(vendor.outstanding_balance),
        }
        return Response(data)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing purchase orders
    """
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related(
            'vendor', 'warehouse', 'created_by'
        ).prefetch_related('lines')
        
        # Filter by status
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by vendor
        vendor_id = self.request.query_params.get('vendor', None)
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
        
        # Filter by date range
        from_date = self.request.query_params.get('from_date', None)
        to_date = self.request.query_params.get('to_date', None)
        
        if from_date:
            queryset = queryset.filter(order_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(order_date__lte=to_date)
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PurchaseOrderDetailSerializer
        return PurchaseOrderSerializer
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a purchase order"""
        order = self.get_object()
        try:
            order.confirm()
            # Create service instance and log
            service = PurchaseOrderService(user=request.user)
            return Response({
                'status': 'success',
                'message': f'Order {order.po_number} confirmed successfully',
                'data': PurchaseOrderSerializer(order).data
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a purchase order"""
        order = self.get_object()
        reason = request.data.get('reason', '')
        
        try:
            order.cancel(user=request.user, reason=reason)
            return Response({
                'status': 'success',
                'message': f'Order {order.po_number} cancelled successfully'
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Receive goods for a purchase order"""
        order = self.get_object()
        receipts_data = request.data.get('receipts', [])
        
        try:
            service = PurchaseOrderService(user=request.user)
            receipt = service.receive_goods(order, receipts_data)
            
            return Response({
                'status': 'success',
                'message': f'Goods received for order {order.po_number}',
                'data': PurchaseReceiptSerializer(receipt).data
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        """Get all lines for a purchase order"""
        order = self.get_object()
        lines = order.lines.all()
        serializer = PurchaseOrderLineSerializer(lines, many=True)
        return Response(serializer.data)


class PurchaseReceiptViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing purchase receipts
    """
    queryset = PurchaseReceipt.objects.all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = PurchaseReceipt.objects.select_related(
            'purchase_order', 'warehouse', 'received_by'
        )
        
        # Filter by status
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by purchase order
        po_id = self.request.query_params.get('purchase_order', None)
        if po_id:
            queryset = queryset.filter(purchase_order_id=po_id)
        
        return queryset


# ===================== Dashboard Views =====================

@staff_member_required
def purchasing_dashboard(request):
    """Purchasing dashboard view"""
    metrics = PurchasingDashboard.get_metrics()
    
    # Get recent activities
    recent_pos = PurchaseOrder.objects.select_related(
        'vendor', 'warehouse'
    ).order_by('-created_at')[:10]
    
    recent_receipts = PurchaseReceipt.objects.select_related(
        'purchase_order', 'received_by'
    ).order_by('-received_date')[:10]
    
    context = {
        'title': 'Purchasing Dashboard',
        'metrics': metrics,
        'recent_pos': recent_pos,
        'recent_receipts': recent_receipts,
        'total_vendors': metrics.get('total_vendors', 0),
        'active_pos': metrics.get('active_pos', 0),
        'pending_receipts': metrics.get('pending_receipts', 0),
        'monthly_purchases': metrics.get('monthly_purchases', 0),
        'top_vendors': metrics.get('top_vendors', []),
    }
    return render(request, 'admin/purchasing/dashboard.html', context)


# ===================== Report Views =====================

@staff_member_required
def purchase_summary_report(request):
    """Purchase summary report"""
    # Get date range from request
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if not from_date:
        from_date = (timezone.now().date() - timedelta(days=30)).isoformat()
    if not to_date:
        to_date = timezone.now().date().isoformat()
    
    # Get purchase orders in date range
    orders = PurchaseOrder.objects.filter(
        order_date__gte=from_date,
        order_date__lte=to_date
    ).select_related('vendor')
    
    # Calculate summary statistics
    total_orders = orders.count()
    total_amount = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Group by status
    status_summary = orders.values('status').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    # Group by vendor
    vendor_summary = orders.values(
        'vendor__id', 'vendor__name'
    ).annotate(
        order_count=Count('id'),
        total_amount=Sum('total_amount')
    ).order_by('-total_amount')[:10]
    
    context = {
        'title': 'Purchase Summary Report',
        'from_date': from_date,
        'to_date': to_date,
        'total_orders': total_orders,
        'total_amount': total_amount,
        'status_summary': status_summary,
        'vendor_summary': vendor_summary,
        'orders': orders[:50],  # Limit to 50 for display
    }
    return render(request, 'admin/purchasing/reports/purchase_summary.html', context)


@staff_member_required
def vendor_performance_report(request):
    """Vendor performance report"""
    vendors = Vendor.objects.annotate(
        order_count=Count('purchase_orders', filter=Q(purchase_orders__status='done')),
        total_purchases=Sum('purchase_orders__total_amount', 
                           filter=Q(purchase_orders__status='done'))
    ).filter(order_count__gt=0)
    
    context = {
        'title': 'Vendor Performance Report',
        'vendors': vendors,
    }
    return render(request, 'admin/purchasing/reports/vendor_performance.html', context)


# ===================== API Helper Views =====================

@staff_member_required
def confirm_purchase_order(request, pk):
    """Confirm purchase order (non-API view)"""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    try:
        order.confirm()
        messages.success(request, f'Order {order.po_number} confirmed successfully')
    except Exception as e:
        messages.error(request, str(e))
    
    return redirect('admin:purchasing_purchaseorder_change', object_id=pk)


@staff_member_required
def cancel_purchase_order(request, pk):
    """Cancel purchase order (non-API view)"""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        try:
            order.cancel(user=request.user, reason=reason)
            messages.success(request, f'Order {order.po_number} cancelled successfully')
        except Exception as e:
            messages.error(request, str(e))
        return redirect('admin:purchasing_purchaseorder_change', object_id=pk)
    
    return render(request, 'admin/purchasing/cancel_order.html', {'order': order})


@staff_member_required
def receive_purchase_order(request, pk):
    """Receive goods for purchase order (non-API view)"""
    # This would redirect to the admin receive view
    return redirect('admin:purchasing_purchaseorder_receive', order_id=pk)