
# sales/views.py
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count
from datetime import date, timedelta
from .models import Customer, SalesOrder, SalesInvoice, Quotation, SalesSettings

@staff_member_required
def dashboard_view(request):
    """Sales dashboard view"""
    today = date.today()
    month_start = date(today.year, today.month, 1)
    week_start = today - timedelta(days=today.weekday())
    
    settings = SalesSettings.get_settings()
    
    context = {
        'title': 'Sales Dashboard',
        'settings': settings,
        
        # Customer stats
        'total_customers': Customer.objects.count(),
        'active_customers': Customer.objects.filter(is_active=True).count(),
        'vip_customers': Customer.objects.filter(is_vip=True).count(),
        
        # Today's stats
        'orders_today': SalesOrder.objects.filter(order_date=today).count(),
        'orders_today_value': SalesOrder.objects.filter(
            order_date=today
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        # This week's stats
        'orders_week': SalesOrder.objects.filter(order_date__gte=week_start).count(),
        'orders_week_value': SalesOrder.objects.filter(
            order_date__gte=week_start
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        # This month's stats
        'orders_month': SalesOrder.objects.filter(order_date__gte=month_start).count(),
        'orders_month_value': SalesOrder.objects.filter(
            order_date__gte=month_start
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        # Invoice stats
        'invoices_unpaid': SalesInvoice.objects.filter(
            status__in=['unpaid', 'partial']
        ).count(),
        'invoices_overdue': SalesInvoice.objects.filter(
            status__in=['unpaid', 'partial'],
            due_date__lt=today
        ).count(),
        'total_receivable': SalesInvoice.objects.filter(
            status__in=['unpaid', 'partial']
        ).aggregate(total=Sum('balance_due'))['total'] or 0,
        
        # Quotation stats
        'quotations_pending': Quotation.objects.filter(
            status='sent'
        ).count() if settings.enable_quotations else 0,
        
        # Recent orders
        'recent_orders': SalesOrder.objects.order_by('-order_date')[:10],
    }
    
    return render(request, 'admin/sales/dashboard.html', context)