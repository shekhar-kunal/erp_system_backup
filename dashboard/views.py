"""Central Dashboard — role-based view routing."""
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from inventory.models import Stock, StockMovement, Warehouse
from products.models import Product, ProductCategory
from purchasing.models import PurchaseOrder, PurchaseOrderLine, Vendor
from sales.models import Customer, SalesOrder, SalesOrderLine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today():
    return timezone.now().date()


def _month_start():
    t = _today()
    return t.replace(day=1)


def _safe_pct(part, whole):
    if not whole:
        return 0
    return round(float(part) / float(whole) * 100, 1)


def _get_role_code(user):
    """Return the user's RBAC role code, or None if no profile/role."""
    if user.is_superuser:
        return 'administrator'
    try:
        profile = user.profile
        if profile.role:
            return profile.role.code
    except Exception:
        pass
    return None


def _build_nav(active, user):
    """Return nav items based on user's role."""
    role = _get_role_code(user)
    is_admin = role in (None, 'administrator')
    is_finance = role == 'finance_manager'
    is_sales = role == 'sales_manager'
    is_purchase = role == 'purchasing_officer'
    is_warehouse = role == 'warehouse_staff'

    ALL_NAV = [
        ('global',     'Global Overview',  'dashboard-global',      '🌐', is_admin or is_finance),
        ('sales',      'Sales',            'dashboard-sales',       '💰', is_admin or is_sales),
        ('inventory',  'Inventory',        'dashboard-inventory',   '📦', is_admin or is_warehouse or is_purchase),
        ('purchasing', 'Purchasing',       'dashboard-purchasing',  '🛒', is_admin or is_purchase),
        ('finance',    'Finance',          'dashboard-finance',     '📑', is_admin or is_finance),
        ('warehouse',  'Warehouse',        'dashboard-warehouse',   '🏭', is_admin or is_warehouse),
        ('reports',    'Reports',          'reports-index',         '📋', True),
    ]

    nav = [
        {'name': name, 'url_name': url, 'icon': icon, 'active': key == active}
        for key, name, url, icon, visible in ALL_NAV
        if visible
    ]
    # Fallback: show all items if nav is empty (unknown role)
    if not nav:
        nav = [
            {'name': name, 'url_name': url, 'icon': icon, 'active': key == active}
            for key, name, url, icon, _ in ALL_NAV
        ]
    return nav


# ---------------------------------------------------------------------------
# Home — redirect by role
# ---------------------------------------------------------------------------

@login_required
def dashboard_home(request):
    role = _get_role_code(request.user)
    ROLE_URLS = {
        'administrator':      'dashboard-global',
        'finance_manager':    'dashboard-finance',
        'sales_manager':      'dashboard-sales',
        'purchasing_officer': 'dashboard-purchasing',
        'warehouse_staff':    'dashboard-warehouse',
    }
    return redirect(ROLE_URLS.get(role, 'dashboard-global'))


# ---------------------------------------------------------------------------
# Global Dashboard (Admin / Management)
# ---------------------------------------------------------------------------

@login_required
def global_dashboard(request):
    today = _today()
    month_start = _month_start()

    # Core counts
    total_products = Product.objects.count()
    total_customers = Customer.objects.count()
    total_vendors = Vendor.objects.count()
    total_warehouses = Warehouse.objects.count()

    # Revenue / expenses (this month)
    month_sales = SalesOrderLine.objects.filter(
        order__status__in=['confirmed', 'completed'],
        order__order_date__gte=month_start,
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    month_purchases = PurchaseOrderLine.objects.filter(
        order__status__in=['confirmed', 'done'],
        order__order_date__gte=month_start,
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    # Gross profit (all time)
    total_sales_all = SalesOrderLine.objects.filter(
        order__status__in=['confirmed', 'completed']
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    gross_profit = SalesOrderLine.objects.filter(
        order__status__in=['confirmed', 'completed']
    ).aggregate(
        profit=Sum((F('price') - F('product__cost')) * F('quantity'))
    )['profit'] or 0

    profit_margin = _safe_pct(gross_profit, total_sales_all)

    # Alerts
    low_stock = Stock.objects.filter(quantity__lt=F('reorder_level')).count()
    out_of_stock = Stock.objects.filter(quantity=0).count()
    pending_sales = SalesOrder.objects.filter(status='confirmed').count()
    pending_purchases = PurchaseOrder.objects.filter(status='confirmed').count()

    # Accounting summary
    try:
        from accounting.models import Invoice, Bill
        unpaid_invoices = Invoice.objects.filter(status__in=['sent', 'partial', 'overdue']).count()
        overdue_invoices = Invoice.objects.filter(status='overdue').count()
        unpaid_bills = Bill.objects.filter(status__in=['received', 'partial', 'overdue']).count()
        invoice_ar = Invoice.objects.filter(
            status__in=['sent', 'partial', 'overdue']
        ).aggregate(ar=Sum(F('total_amount') - F('amount_paid')))['ar'] or 0
    except Exception:
        unpaid_invoices = overdue_invoices = unpaid_bills = 0
        invoice_ar = 0

    # 30-day revenue vs cost trend
    labels_30, revenue_30, cost_30 = [], [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        labels_30.append(d.strftime('%b %d'))
        rev = SalesOrderLine.objects.filter(
            order__status__in=['confirmed', 'completed'],
            order__order_date=d,
        ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0
        cst = PurchaseOrderLine.objects.filter(
            order__status__in=['confirmed', 'done'],
            order__order_date=d,
        ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0
        revenue_30.append(float(rev))
        cost_30.append(float(cst))

    # Sales by status (doughnut)
    status_data = list(SalesOrder.objects.values('status').annotate(cnt=Count('id')))
    status_labels = [d['status'].title() for d in status_data]
    status_counts = [d['cnt'] for d in status_data]

    context = {
        'nav': _build_nav('global', request.user),
        'today': today,
        'total_products': total_products,
        'total_customers': total_customers,
        'total_vendors': total_vendors,
        'total_warehouses': total_warehouses,
        'month_sales': month_sales,
        'month_purchases': month_purchases,
        'gross_profit': gross_profit,
        'profit_margin': profit_margin,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'pending_sales': pending_sales,
        'pending_purchases': pending_purchases,
        'unpaid_invoices': unpaid_invoices,
        'overdue_invoices': overdue_invoices,
        'unpaid_bills': unpaid_bills,
        'invoice_ar': invoice_ar,
        'chart_labels': json.dumps(labels_30),
        'chart_revenue': json.dumps(revenue_30),
        'chart_cost': json.dumps(cost_30),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
    }
    return render(request, 'dashboard/global.html', context)


# ---------------------------------------------------------------------------
# Sales Dashboard
# ---------------------------------------------------------------------------

@login_required
def sales_dashboard(request):
    today = _today()
    month_start = _month_start()

    today_revenue = SalesOrderLine.objects.filter(
        order__status__in=['confirmed', 'completed'],
        order__order_date=today,
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    month_revenue = SalesOrderLine.objects.filter(
        order__status__in=['confirmed', 'completed'],
        order__order_date__gte=month_start,
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    draft_orders = SalesOrder.objects.filter(status='draft').count()
    confirmed_orders = SalesOrder.objects.filter(status='confirmed').count()
    completed_orders = SalesOrder.objects.filter(status='completed').count()
    cancelled_orders = SalesOrder.objects.filter(status='cancelled').count()
    total_customers = Customer.objects.count()

    top_customers = Customer.objects.annotate(
        total_sales=Sum(
            F('sales_orders__lines__quantity') * F('sales_orders__lines__price')
        )
    ).filter(total_sales__isnull=False).order_by('-total_sales')[:8]

    recent_orders = SalesOrder.objects.select_related('customer').order_by('-order_date', '-id')[:10]

    # 7-day trend
    labels_7, sales_7 = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        labels_7.append(d.strftime('%a %d'))
        rev = SalesOrderLine.objects.filter(
            order__status__in=['confirmed', 'completed'],
            order__order_date=d,
        ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0
        sales_7.append(float(rev))

    status_labels = ['Draft', 'Confirmed', 'Completed', 'Cancelled']
    status_counts = [draft_orders, confirmed_orders, completed_orders, cancelled_orders]

    context = {
        'nav': _build_nav('sales', request.user),
        'today': today,
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'draft_orders': draft_orders,
        'confirmed_orders': confirmed_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'total_customers': total_customers,
        'top_customers': top_customers,
        'recent_orders': recent_orders,
        'chart_labels': json.dumps(labels_7),
        'chart_sales': json.dumps(sales_7),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
    }
    return render(request, 'dashboard/sales.html', context)


# ---------------------------------------------------------------------------
# Inventory Dashboard
# ---------------------------------------------------------------------------

@login_required
def inventory_dashboard(request):
    today = _today()

    total_sku = Stock.objects.count()
    low_stock = Stock.objects.filter(quantity__lt=F('reorder_level'), quantity__gt=0).count()
    out_of_stock = Stock.objects.filter(quantity=0).count()
    total_value = Stock.objects.aggregate(
        v=Sum(F('quantity') * F('product__cost'))
    )['v'] or 0

    low_stock_items = Stock.objects.select_related('product', 'warehouse').filter(
        quantity__lt=F('reorder_level')
    ).order_by('quantity')[:10]

    warehouses = Warehouse.objects.annotate(
        wh_count=Count('stock_entries', distinct=True),
        wh_value=Sum(F('stock_entries__quantity') * F('stock_entries__product__cost')),
        wh_qty=Sum('stock_entries__quantity'),
    ).order_by('-wh_value')

    recent_movements = StockMovement.objects.select_related(
        'product', 'warehouse'
    ).order_by('-created_at')[:15]

    # 7-day movement trend
    labels_7, in_7, out_7 = [], [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        labels_7.append(d.strftime('%a %d'))
        in_q = StockMovement.objects.filter(
            movement_type='IN', created_at__date=d
        ).aggregate(q=Sum('quantity'))['q'] or 0
        out_q = StockMovement.objects.filter(
            movement_type='OUT', created_at__date=d
        ).aggregate(q=Sum('quantity'))['q'] or 0
        in_7.append(float(in_q))
        out_7.append(float(out_q))

    wh_labels = [w.name for w in warehouses]
    wh_values = [float(w.wh_value or 0) for w in warehouses]

    context = {
        'nav': _build_nav('inventory', request.user),
        'today': today,
        'total_sku': total_sku,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'total_value': total_value,
        'low_stock_items': low_stock_items,
        'warehouses': warehouses,
        'recent_movements': recent_movements,
        'chart_labels': json.dumps(labels_7),
        'chart_in': json.dumps(in_7),
        'chart_out': json.dumps(out_7),
        'wh_labels': json.dumps(wh_labels),
        'wh_values': json.dumps(wh_values),
    }
    return render(request, 'dashboard/inventory.html', context)


# ---------------------------------------------------------------------------
# Purchasing Dashboard
# ---------------------------------------------------------------------------

@login_required
def purchasing_dashboard(request):
    today = _today()
    month_start = _month_start()

    draft_pos = PurchaseOrder.objects.filter(status='draft').count()
    confirmed_pos = PurchaseOrder.objects.filter(status='confirmed').count()
    done_pos = PurchaseOrder.objects.filter(status='done').count()

    month_spend = PurchaseOrderLine.objects.filter(
        order__status__in=['confirmed', 'done'],
        order__order_date__gte=month_start,
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0

    top_vendors = Vendor.objects.annotate(
        spend_total=Sum(
            F('purchase_orders__lines__quantity') * F('purchase_orders__lines__price')
        )
    ).filter(spend_total__isnull=False).order_by('-spend_total')[:8]

    recent_pos = PurchaseOrder.objects.select_related('vendor').order_by('-order_date', '-id')[:10]

    # 7-day spend trend
    labels_7, spend_7 = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        labels_7.append(d.strftime('%a %d'))
        spnd = PurchaseOrderLine.objects.filter(
            order__status__in=['confirmed', 'done'],
            order__order_date=d,
        ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0
        spend_7.append(float(spnd))

    status_labels = ['Draft', 'Confirmed', 'Done']
    status_counts = [draft_pos, confirmed_pos, done_pos]

    context = {
        'nav': _build_nav('purchasing', request.user),
        'today': today,
        'draft_pos': draft_pos,
        'confirmed_pos': confirmed_pos,
        'done_pos': done_pos,
        'month_spend': month_spend,
        'top_vendors': top_vendors,
        'recent_pos': recent_pos,
        'chart_labels': json.dumps(labels_7),
        'chart_spend': json.dumps(spend_7),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
    }
    return render(request, 'dashboard/purchasing.html', context)


# ---------------------------------------------------------------------------
# Finance Dashboard
# ---------------------------------------------------------------------------

@login_required
def finance_dashboard(request):
    today = _today()

    try:
        from accounting.models import Invoice, Bill

        invoices_draft = Invoice.objects.filter(status='draft').count()
        invoices_sent = Invoice.objects.filter(status='sent').count()
        invoices_partial = Invoice.objects.filter(status='partial').count()
        invoices_paid = Invoice.objects.filter(status='paid').count()
        invoices_overdue = Invoice.objects.filter(status='overdue').count()

        total_invoiced = Invoice.objects.filter(
            status__in=['sent', 'partial', 'paid', 'overdue']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        total_received = Invoice.objects.aggregate(total=Sum('amount_paid'))['total'] or 0
        ar_balance = float(total_invoiced) - float(total_received)

        bills_draft = Bill.objects.filter(status='draft').count()
        bills_received = Bill.objects.filter(status='received').count()
        bills_partial = Bill.objects.filter(status='partial').count()
        bills_paid = Bill.objects.filter(status='paid').count()
        bills_overdue = Bill.objects.filter(status='overdue').count()

        total_billed = Bill.objects.filter(
            status__in=['received', 'partial', 'paid', 'overdue']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid_out = Bill.objects.aggregate(total=Sum('amount_paid'))['total'] or 0
        ap_balance = float(total_billed) - float(total_paid_out)

        overdue_list = Invoice.objects.select_related('customer').filter(
            status='overdue'
        ).order_by('due_date')[:10]

        upcoming_bills = Bill.objects.select_related('vendor').filter(
            status__in=['received', 'partial'],
            due_date__gte=today,
        ).order_by('due_date')[:10]

        # 30-day invoice vs bill trend
        labels_30, inv_trend, bill_trend = [], [], []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            labels_30.append(d.strftime('%b %d'))
            inv = Invoice.objects.filter(invoice_date=d).aggregate(
                total=Sum('total_amount'))['total'] or 0
            bil = Bill.objects.filter(bill_date=d).aggregate(
                total=Sum('total_amount'))['total'] or 0
            inv_trend.append(float(inv))
            bill_trend.append(float(bil))

    except Exception:
        invoices_draft = invoices_sent = invoices_partial = invoices_paid = invoices_overdue = 0
        total_invoiced = total_received = ar_balance = 0
        bills_draft = bills_received = bills_partial = bills_paid = bills_overdue = 0
        total_billed = total_paid_out = ap_balance = 0
        overdue_list = []
        upcoming_bills = []
        labels_30 = [(today - timedelta(days=i)).strftime('%b %d') for i in range(29, -1, -1)]
        inv_trend = [0] * 30
        bill_trend = [0] * 30

    context = {
        'nav': _build_nav('finance', request.user),
        'today': today,
        'invoices_draft': invoices_draft,
        'invoices_sent': invoices_sent,
        'invoices_partial': invoices_partial,
        'invoices_paid': invoices_paid,
        'invoices_overdue': invoices_overdue,
        'total_invoiced': total_invoiced,
        'total_received': total_received,
        'ar_balance': ar_balance,
        'bills_draft': bills_draft,
        'bills_received': bills_received,
        'bills_partial': bills_partial,
        'bills_paid': bills_paid,
        'bills_overdue': bills_overdue,
        'total_billed': total_billed,
        'total_paid_out': total_paid_out,
        'ap_balance': ap_balance,
        'overdue_list': overdue_list,
        'upcoming_bills': upcoming_bills,
        'chart_labels': json.dumps(labels_30),
        'chart_inv': json.dumps(inv_trend),
        'chart_bill': json.dumps(bill_trend),
    }
    return render(request, 'dashboard/finance.html', context)


# ---------------------------------------------------------------------------
# Warehouse Dashboard
# ---------------------------------------------------------------------------

@login_required
def warehouse_dashboard(request):
    today = _today()

    warehouses = Warehouse.objects.annotate(
        wh_items=Count('stock_entries', distinct=True),
        wh_qty=Sum('stock_entries__quantity'),
        wh_value=Sum(F('stock_entries__quantity') * F('stock_entries__product__cost')),
        low_count=Count(
            'stock_entries',
            filter=Q(stock_entries__quantity__lt=F('stock_entries__reorder_level')),
        ),
    ).order_by('name')

    total_value = Stock.objects.aggregate(
        v=Sum(F('quantity') * F('product__cost'))
    )['v'] or 0
    total_items = Stock.objects.count()
    low_stock_total = Stock.objects.filter(quantity__lt=F('reorder_level')).count()

    recent_movements = StockMovement.objects.select_related(
        'product', 'warehouse'
    ).order_by('-created_at')[:20]

    # 7-day movement trend
    labels_7, in_7, out_7 = [], [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        labels_7.append(d.strftime('%a %d'))
        in_q = StockMovement.objects.filter(
            movement_type='IN', created_at__date=d
        ).aggregate(q=Sum('quantity'))['q'] or 0
        out_q = StockMovement.objects.filter(
            movement_type='OUT', created_at__date=d
        ).aggregate(q=Sum('quantity'))['q'] or 0
        in_7.append(float(in_q))
        out_7.append(float(out_q))

    wh_labels = [w.name for w in warehouses]
    wh_items = [w.wh_items or 0 for w in warehouses]
    wh_values = [float(w.wh_value or 0) for w in warehouses]

    context = {
        'nav': _build_nav('warehouse', request.user),
        'today': today,
        'warehouses': warehouses,
        'total_value': total_value,
        'total_items': total_items,
        'low_stock_total': low_stock_total,
        'recent_movements': recent_movements,
        'chart_labels': json.dumps(labels_7),
        'chart_in': json.dumps(in_7),
        'chart_out': json.dumps(out_7),
        'wh_labels': json.dumps(wh_labels),
        'wh_items': json.dumps(wh_items),
        'wh_values': json.dumps(wh_values),
    }
    return render(request, 'dashboard/warehouse.html', context)


# ---------------------------------------------------------------------------
# Legacy — kept for any direct references
# ---------------------------------------------------------------------------

def dashboard_view(request):
    """Backwards-compat redirect to role-based home."""
    if request.user.is_authenticated:
        return dashboard_home(request)
    from django.contrib.auth.views import redirect_to_login
    return redirect_to_login(request.get_full_path())
