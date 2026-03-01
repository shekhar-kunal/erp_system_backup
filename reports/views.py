"""
Reports & Analytics — all report views.
Each view:
  1. Checks RBAC access
  2. Parses filter form
  3. Builds columns + rows
  4. Returns file download if ?export= present, else renders report_base.html
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, ExpressionWrapper, F, Max, Q, Sum, DecimalField
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import (
    AgingFilterForm, CustomerSalesFilterForm, CustomReportForm,
    InventoryFilterForm, MovementFilterForm, ProfitFilterForm,
    PurchaseFilterForm, SalesFilterForm, SupplierFilterForm,
    TaxFilterForm, TopProductsFilterForm, WarehouseFilterForm,
)
from .utils import export_report

# ─────────────────────────────────────────────────────────────
# RBAC helpers
# ─────────────────────────────────────────────────────────────

REPORT_ROLES = {
    'inventory-valuation':  ['administrator', 'warehouse_staff', 'purchasing_officer'],
    'stock-aging':          ['administrator', 'warehouse_staff'],
    'low-stock':            ['administrator', 'warehouse_staff', 'purchasing_officer'],
    'sales':                ['administrator', 'sales_manager'],
    'customer-sales':       ['administrator', 'sales_manager'],
    'top-products':         ['administrator', 'sales_manager', 'purchasing_officer'],
    'purchases':            ['administrator', 'purchasing_officer'],
    'supplier':             ['administrator', 'purchasing_officer'],
    'warehouse-movement':   ['administrator', 'warehouse_staff'],
    'profit':               ['administrator', 'finance_manager'],
    'ar-aging':             ['administrator', 'finance_manager'],
    'ap-aging':             ['administrator', 'finance_manager'],
    'tax':                  ['administrator', 'finance_manager'],
    'custom':               ['administrator', 'finance_manager'],
}

# Report metadata for the index page and sidebar
REPORT_META = [
    # (key, title, url_name, icon, description, category)
    ('inventory-valuation',  'Inventory Valuation',       'report-inventory-valuation',  '📦', 'Stock value at cost price, grouped by product, category, and warehouse.', 'Inventory'),
    ('stock-aging',          'Stock Aging',               'report-stock-aging',          '⏳', 'How long stock batches have been held, bucketed into age ranges.', 'Inventory'),
    ('low-stock',            'Low Stock & Reorder',       'report-low-stock',            '⚠️', 'Products below reorder level with suggested reorder quantities.', 'Inventory'),
    ('sales',                'Sales Report',              'report-sales',                '💰', 'Revenue by period (daily/monthly/yearly) with tax and discount breakdown.', 'Sales'),
    ('customer-sales',       'Customer Sales',            'report-customer-sales',       '👥', 'Per-customer order count, revenue, average order value, and last order date.', 'Sales'),
    ('top-products',         'Top Products',              'report-top-products',         '🏆', 'Best-selling products ranked by quantity sold and revenue.', 'Sales'),
    ('purchases',            'Purchase Report',           'report-purchases',            '🛒', 'Purchasing spend by period with vendor and status filters.', 'Purchasing'),
    ('supplier',             'Supplier Report',           'report-supplier',             '🏭', 'Per-vendor PO count, total spend, average PO value, and last order date.', 'Purchasing'),
    ('warehouse-movement',   'Warehouse Movement',        'report-warehouse-movement',   '🔄', 'All stock movements (IN/OUT/Transfer/Adjustment) in a date range.', 'Warehouse'),
    ('profit',               'Profit Analysis',           'report-profit',               '📈', 'Gross profit and margin by product or category.', 'Finance'),
    ('ar-aging',             'AR Aging',                  'report-ar-aging',             '🧾', 'Outstanding invoice balances bucketed by days overdue (0-30-60-90+).', 'Finance'),
    ('ap-aging',             'AP Aging',                  'report-ap-aging',             '📤', 'Outstanding bill balances bucketed by days overdue (0-30-60-90+).', 'Finance'),
    ('tax',                  'Tax Report',                'report-tax',                  '🏛️', 'Tax collected on sales vs tax paid on purchases, and net tax payable.', 'Finance'),
    ('custom',               'Custom Report Builder',     'report-custom',               '⚙️', 'Build ad-hoc reports by selecting entity, date range, and grouping.', 'Custom'),
]


def _get_role_code(user):
    if user.is_superuser:
        return 'administrator'
    try:
        return user.profile.role.code
    except Exception:
        return None


def _can_access(user, report_key):
    role = _get_role_code(user)
    return role in REPORT_ROLES.get(report_key, [])


def _build_report_nav(user):
    """Return sidebar nav items for the reports app."""
    role = _get_role_code(user)
    nav = []
    for key, title, url_name, icon, _, category in REPORT_META:
        allowed = REPORT_ROLES.get(key, [])
        if role in allowed:
            nav.append({'key': key, 'title': title, 'url_name': url_name, 'icon': icon, 'category': category})
    return nav


def _render_report(request, title, columns, rows, summary, form, report_key, export_fmt=None):
    """Helper: either return file download or render report_base.html."""
    if export_fmt:
        return export_report(title, columns, rows, export_fmt, summary)
    return render(request, 'reports/report_base.html', {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
        'form': form,
        'report_nav': _build_report_nav(request.user),
        'report_key': report_key,
    })


def _deny(request):
    messages.error(request, 'You do not have permission to access this report.')
    return redirect('reports-index')


def _today():
    return timezone.now().date()


# ─────────────────────────────────────────────────────────────
# Index
# ─────────────────────────────────────────────────────────────

@login_required
def report_index(request):
    role = _get_role_code(request.user)
    # Build categorized list of accessible reports
    categories = {}
    for key, title, url_name, icon, desc, category in REPORT_META:
        if role in REPORT_ROLES.get(key, []):
            categories.setdefault(category, []).append({
                'key': key, 'title': title, 'url_name': url_name,
                'icon': icon, 'desc': desc,
            })
    return render(request, 'reports/index.html', {
        'categories': categories,
        'report_nav': _build_report_nav(request.user),
    })


# ─────────────────────────────────────────────────────────────
# 1. Inventory Valuation
# ─────────────────────────────────────────────────────────────

@login_required
def inventory_valuation(request):
    if not _can_access(request.user, 'inventory-valuation'):
        return _deny(request)

    from inventory.models import Stock
    form = InventoryFilterForm(request.GET or None)
    qs = Stock.objects.select_related(
        'product', 'warehouse', 'product__category'
    ).annotate(
        stock_value=ExpressionWrapper(
            F('quantity') * F('product__cost'), output_field=DecimalField(max_digits=15, decimal_places=2)
        )
    )
    if form.is_valid():
        if form.cleaned_data.get('warehouse'):
            qs = qs.filter(warehouse=form.cleaned_data['warehouse'])
        if form.cleaned_data.get('category'):
            qs = qs.filter(product__category=form.cleaned_data['category'])

    columns = ['Product', 'SKU', 'Category', 'Warehouse', 'Qty', 'Unit Cost', 'Total Value']
    rows = []
    total_value = Decimal('0')
    for s in qs.order_by('product__name'):
        cat = s.product.category.name if s.product.category else '—'
        val = s.stock_value or Decimal('0')
        total_value += val
        rows.append([s.product.name, s.product.sku or s.product.code, cat,
                      s.warehouse.name, s.quantity, s.product.cost, val])

    summary = {'Total SKUs': len(rows), 'Total Value': total_value}
    return _render_report(request, 'Inventory Valuation Report', columns, rows, summary,
                          form, 'inventory-valuation', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 2. Stock Aging
# ─────────────────────────────────────────────────────────────

@login_required
def stock_aging(request):
    if not _can_access(request.user, 'stock-aging'):
        return _deny(request)

    from inventory.models import StockBatch
    form = WarehouseFilterForm(request.GET or None)
    today = _today()

    qs = StockBatch.objects.select_related(
        'stock__product', 'stock__warehouse'
    ).filter(is_active=True, quantity__gt=0)

    if form.is_valid() and form.cleaned_data.get('warehouse'):
        qs = qs.filter(stock__warehouse=form.cleaned_data['warehouse'])

    columns = ['Product', 'Warehouse', 'Batch', 'Received Date', 'Age (Days)', 'Age Bucket', 'Qty', 'Value']
    rows = []
    bucket_totals = {'0-30': Decimal('0'), '31-60': Decimal('0'), '61-90': Decimal('0'), '90+': Decimal('0')}

    for b in qs.order_by('received_date'):
        age = (today - b.received_date).days
        if age <= 30:
            bucket = '0-30 days'
            bk = '0-30'
        elif age <= 60:
            bucket = '31-60 days'
            bk = '31-60'
        elif age <= 90:
            bucket = '61-90 days'
            bk = '61-90'
        else:
            bucket = '90+ days'
            bk = '90+'
        cost = b.stock.product.cost if hasattr(b.stock.product, 'cost') else Decimal('0')
        val = b.quantity * cost
        bucket_totals[bk] += val
        rows.append([b.stock.product.name, b.stock.warehouse.name, b.batch_number,
                      b.received_date, age, bucket, b.quantity, val])

    summary = {
        '0-30 Days Value': bucket_totals['0-30'],
        '31-60 Days Value': bucket_totals['31-60'],
        '61-90 Days Value': bucket_totals['61-90'],
        '90+ Days Value': bucket_totals['90+'],
        'Total Batches': len(rows),
    }
    return _render_report(request, 'Stock Aging Report', columns, rows, summary,
                          form, 'stock-aging', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 3. Low Stock / Reorder Suggestions
# ─────────────────────────────────────────────────────────────

@login_required
def low_stock(request):
    if not _can_access(request.user, 'low-stock'):
        return _deny(request)

    from inventory.models import Stock
    form = WarehouseFilterForm(request.GET or None)
    qs = Stock.objects.select_related('product', 'warehouse').filter(
        quantity__lt=F('reorder_level')
    )
    if form.is_valid() and form.cleaned_data.get('warehouse'):
        qs = qs.filter(warehouse=form.cleaned_data['warehouse'])

    columns = ['Product', 'SKU', 'Warehouse', 'On Hand', 'Reorder Level', 'Shortage', 'Suggested Order']
    rows = []
    for s in qs.order_by('quantity'):
        shortage = s.reorder_level - s.quantity
        suggested = shortage * Decimal('1.5')  # 1.5× shortage as buffer
        rows.append([s.product.name, s.product.sku or s.product.code,
                      s.warehouse.name, s.quantity, s.reorder_level, shortage, suggested])

    summary = {
        'Total Low Stock Items': len(rows),
        'Out of Stock': sum(1 for r in rows if r[3] == 0),
    }
    return _render_report(request, 'Low Stock & Reorder Suggestions', columns, rows, summary,
                          form, 'low-stock', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 4. Sales Report
# ─────────────────────────────────────────────────────────────

@login_required
def sales_report(request):
    if not _can_access(request.user, 'sales'):
        return _deny(request)

    from sales.models import SalesOrder
    form = SalesFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )
    period = (form.cleaned_data.get('period') or 'month') if form.is_valid() else 'month'

    trunc_fn = {'day': TruncDay, 'month': TruncMonth, 'year': TruncYear}.get(period, TruncMonth)

    qs = SalesOrder.objects.filter(
        order_date__gte=date_from, order_date__lte=date_to,
        status__in=['confirmed', 'completed', 'invoiced'],
    )
    if form.is_valid():
        if form.cleaned_data.get('customer'):
            qs = qs.filter(customer=form.cleaned_data['customer'])
        if form.cleaned_data.get('status'):
            qs = qs.filter(status=form.cleaned_data['status'])

    data = (
        qs.annotate(period_group=trunc_fn('order_date'))
        .values('period_group')
        .annotate(
            order_count=Count('id', distinct=True),
            revenue=Sum('subtotal'),
            tax=Sum('tax_amount'),
            discount=Sum('discount_amount'),
        )
        .order_by('period_group')
    )

    columns = ['Period', 'Orders', 'Revenue', 'Tax', 'Discount', 'Net Revenue']
    rows = []
    total_revenue = Decimal('0')
    total_tax = Decimal('0')
    for d in data:
        rev = d['revenue'] or Decimal('0')
        tax = d['tax'] or Decimal('0')
        disc = d['discount'] or Decimal('0')
        net = rev - disc
        total_revenue += rev
        total_tax += tax
        period_label = d['period_group'].strftime('%Y-%m-%d') if d['period_group'] else '—'
        rows.append([period_label, d['order_count'], rev, tax, disc, net])

    summary = {
        'Total Orders': qs.count(),
        'Total Revenue': total_revenue,
        'Total Tax': total_tax,
        'Net Revenue': total_revenue - (sum(r[4] for r in rows)),
    }
    return _render_report(request, 'Sales Report', columns, rows, summary,
                          form, 'sales', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 5. Customer Sales
# ─────────────────────────────────────────────────────────────

@login_required
def customer_sales(request):
    if not _can_access(request.user, 'customer-sales'):
        return _deny(request)

    from sales.models import Customer, SalesOrderLine
    form = CustomerSalesFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )

    data = Customer.objects.annotate(
        order_count=Count('sales_orders', filter=Q(
            sales_orders__order_date__gte=date_from,
            sales_orders__order_date__lte=date_to,
            sales_orders__status__in=['confirmed', 'completed', 'invoiced'],
        ), distinct=True),
        revenue=Sum(
            F('sales_orders__lines__quantity') * F('sales_orders__lines__price'),
            filter=Q(
                sales_orders__order_date__gte=date_from,
                sales_orders__order_date__lte=date_to,
                sales_orders__status__in=['confirmed', 'completed', 'invoiced'],
            ),
        ),
        last_order=Max('sales_orders__order_date'),
    ).filter(order_count__gt=0).order_by('-revenue')

    columns = ['Customer', 'Email', 'Orders', 'Total Revenue', 'Avg Order Value', 'Last Order']
    rows = []
    total_revenue = Decimal('0')
    for c in data:
        rev = c.revenue or Decimal('0')
        avg = rev / c.order_count if c.order_count else Decimal('0')
        total_revenue += rev
        rows.append([c.full_name, c.email, c.order_count, rev, avg,
                      c.last_order.strftime('%Y-%m-%d') if c.last_order else '—'])

    summary = {'Total Customers': len(rows), 'Total Revenue': total_revenue}
    return _render_report(request, 'Customer Sales Report', columns, rows, summary,
                          form, 'customer-sales', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 6. Top Products
# ─────────────────────────────────────────────────────────────

@login_required
def top_products(request):
    if not _can_access(request.user, 'top-products'):
        return _deny(request)

    from sales.models import SalesOrderLine
    form = TopProductsFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )

    filters = Q(
        order__order_date__gte=date_from,
        order__order_date__lte=date_to,
        order__status__in=['confirmed', 'completed', 'invoiced'],
    )
    if form.is_valid() and form.cleaned_data.get('category'):
        filters &= Q(product__category=form.cleaned_data['category'])

    data = (
        SalesOrderLine.objects.filter(filters)
        .values('product__name', 'product__category__name', 'product__sku')
        .annotate(
            qty_sold=Sum('quantity'),
            revenue=Sum(F('quantity') * F('price')),
            avg_price=Avg('price'),
        )
        .order_by('-revenue')[:50]
    )

    columns = ['#', 'Product', 'SKU', 'Category', 'Qty Sold', 'Revenue', 'Avg Price']
    rows = []
    for i, d in enumerate(data, 1):
        rows.append([i, d['product__name'], d['product__sku'] or '—',
                      d['product__category__name'] or '—',
                      d['qty_sold'] or 0, d['revenue'] or Decimal('0'),
                      d['avg_price'] or Decimal('0')])

    summary = {
        'Products Sold': len(rows),
        'Total Revenue': sum(r[5] for r in rows),
        'Total Qty': sum(r[4] for r in rows),
    }
    return _render_report(request, 'Top Products Report', columns, rows, summary,
                          form, 'top-products', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 7. Purchase Report
# ─────────────────────────────────────────────────────────────

@login_required
def purchase_report(request):
    if not _can_access(request.user, 'purchases'):
        return _deny(request)

    from purchasing.models import PurchaseOrder
    form = PurchaseFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )
    period = (form.cleaned_data.get('period') or 'month') if form.is_valid() else 'month'
    trunc_fn = {'day': TruncDay, 'month': TruncMonth, 'year': TruncYear}.get(period, TruncMonth)

    qs = PurchaseOrder.objects.filter(
        order_date__gte=date_from, order_date__lte=date_to,
        status__in=['confirmed', 'partial', 'done'],
    )
    if form.is_valid():
        if form.cleaned_data.get('vendor'):
            qs = qs.filter(vendor=form.cleaned_data['vendor'])
        if form.cleaned_data.get('status'):
            qs = qs.filter(status=form.cleaned_data['status'])

    data = (
        qs.annotate(period_group=trunc_fn('order_date'))
        .values('period_group')
        .annotate(
            po_count=Count('id', distinct=True),
            spend=Sum('subtotal'),
            tax=Sum('tax_amount'),
            discount=Sum('discount_amount'),
        )
        .order_by('period_group')
    )

    columns = ['Period', 'POs', 'Spend', 'Tax', 'Discount', 'Net Spend']
    rows = []
    total_spend = Decimal('0')
    for d in data:
        spnd = d['spend'] or Decimal('0')
        tax = d['tax'] or Decimal('0')
        disc = d['discount'] or Decimal('0')
        net = spnd - disc
        total_spend += spnd
        period_label = d['period_group'].strftime('%Y-%m-%d') if d['period_group'] else '—'
        rows.append([period_label, d['po_count'], spnd, tax, disc, net])

    summary = {
        'Total POs': qs.count(),
        'Total Spend': total_spend,
        'Net Spend': total_spend - sum(r[4] for r in rows),
    }
    return _render_report(request, 'Purchase Report', columns, rows, summary,
                          form, 'purchases', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 8. Supplier Report
# ─────────────────────────────────────────────────────────────

@login_required
def supplier_report(request):
    if not _can_access(request.user, 'supplier'):
        return _deny(request)

    from purchasing.models import Vendor
    form = SupplierFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )

    data = Vendor.objects.annotate(
        po_count=Count('purchase_orders', filter=Q(
            purchase_orders__order_date__gte=date_from,
            purchase_orders__order_date__lte=date_to,
            purchase_orders__status__in=['confirmed', 'partial', 'done'],
        ), distinct=True),
        total_spend=Sum(
            'purchase_orders__subtotal',
            filter=Q(
                purchase_orders__order_date__gte=date_from,
                purchase_orders__order_date__lte=date_to,
                purchase_orders__status__in=['confirmed', 'partial', 'done'],
            ),
        ),
        last_po=Max('purchase_orders__order_date'),
    ).filter(po_count__gt=0).order_by('-total_spend')

    columns = ['Vendor', 'Contact', 'POs', 'Total Spend', 'Avg PO Value', 'Last PO']
    rows = []
    grand_total = Decimal('0')
    for v in data:
        spnd = v.total_spend or Decimal('0')
        avg = spnd / v.po_count if v.po_count else Decimal('0')
        grand_total += spnd
        rows.append([v.name, v.contact_person or '—', v.po_count, spnd, avg,
                      v.last_po.strftime('%Y-%m-%d') if v.last_po else '—'])

    summary = {'Active Vendors': len(rows), 'Total Spend': grand_total}
    return _render_report(request, 'Supplier Report', columns, rows, summary,
                          form, 'supplier', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 9. Warehouse Movement
# ─────────────────────────────────────────────────────────────

@login_required
def warehouse_movement(request):
    if not _can_access(request.user, 'warehouse-movement'):
        return _deny(request)

    from inventory.models import StockMovement
    form = MovementFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )

    qs = StockMovement.objects.select_related('product', 'warehouse').filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if form.is_valid():
        if form.cleaned_data.get('warehouse'):
            qs = qs.filter(warehouse=form.cleaned_data['warehouse'])
        if form.cleaned_data.get('movement_type'):
            qs = qs.filter(movement_type=form.cleaned_data['movement_type'])

    columns = ['Date', 'Product', 'Warehouse', 'Type', 'Source', 'Qty', 'Reference']
    rows = []
    total_in = Decimal('0')
    total_out = Decimal('0')
    for m in qs.order_by('-created_at')[:500]:
        if m.movement_type in ('IN', 'TRANSFER_IN', 'RETURN'):
            total_in += m.quantity
        else:
            total_out += m.quantity
        rows.append([
            m.created_at.strftime('%Y-%m-%d %H:%M'),
            m.product.name,
            m.warehouse.name,
            m.movement_type,
            m.source or '—',
            m.quantity,
            m.reference or '—',
        ])

    summary = {
        'Total Movements': len(rows),
        'Total In': total_in,
        'Total Out': total_out,
        'Net': total_in - total_out,
    }
    return _render_report(request, 'Warehouse Movement Report', columns, rows, summary,
                          form, 'warehouse-movement', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 10. Profit Analysis
# ─────────────────────────────────────────────────────────────

@login_required
def profit_analysis(request):
    if not _can_access(request.user, 'profit'):
        return _deny(request)

    from sales.models import SalesOrderLine
    form = ProfitFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )
    group_by = (form.cleaned_data.get('group_by') or 'product') if form.is_valid() else 'product'

    base_filter = Q(
        order__status__in=['confirmed', 'completed', 'invoiced'],
        order__order_date__gte=date_from,
        order__order_date__lte=date_to,
    )

    if group_by == 'category':
        data = (
            SalesOrderLine.objects.filter(base_filter)
            .values('product__category__name')
            .annotate(
                revenue=Sum(F('quantity') * F('price')),
                cost=Sum(F('quantity') * F('cost_price')),
                gross_profit=Sum((F('price') - F('cost_price')) * F('quantity')),
                qty=Sum('quantity'),
            )
            .order_by('-gross_profit')
        )
        columns = ['Category', 'Qty Sold', 'Revenue', 'Cost', 'Gross Profit', 'Margin %']
        rows = []
        for d in data:
            rev = d['revenue'] or Decimal('0')
            gp = d['gross_profit'] or Decimal('0')
            margin = round(float(gp) / float(rev) * 100, 1) if rev else 0
            rows.append([d['product__category__name'] or 'Uncategorised',
                          d['qty'] or 0, rev, d['cost'] or Decimal('0'), gp, f'{margin}%'])
    else:
        data = (
            SalesOrderLine.objects.filter(base_filter)
            .values('product__name', 'product__sku', 'product__category__name')
            .annotate(
                revenue=Sum(F('quantity') * F('price')),
                cost=Sum(F('quantity') * F('cost_price')),
                gross_profit=Sum((F('price') - F('cost_price')) * F('quantity')),
                qty=Sum('quantity'),
            )
            .order_by('-gross_profit')
        )
        columns = ['Product', 'SKU', 'Category', 'Qty Sold', 'Revenue', 'Cost', 'Gross Profit', 'Margin %']
        rows = []
        for d in data:
            rev = d['revenue'] or Decimal('0')
            gp = d['gross_profit'] or Decimal('0')
            margin = round(float(gp) / float(rev) * 100, 1) if rev else 0
            rows.append([d['product__name'], d['product__sku'] or '—',
                          d['product__category__name'] or '—',
                          d['qty'] or 0, rev, d['cost'] or Decimal('0'), gp, f'{margin}%'])

    total_rev = sum(r[-4] for r in rows) if rows else Decimal('0')
    total_gp = sum(r[-2] for r in rows) if rows else Decimal('0')
    overall_margin = round(float(total_gp) / float(total_rev) * 100, 1) if total_rev else 0

    summary = {
        'Total Revenue': total_rev,
        'Total Gross Profit': total_gp,
        'Overall Margin': f'{overall_margin}%',
    }
    return _render_report(request, 'Profit Analysis', columns, rows, summary,
                          form, 'profit', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 11. AR Aging
# ─────────────────────────────────────────────────────────────

@login_required
def ar_aging(request):
    if not _can_access(request.user, 'ar-aging'):
        return _deny(request)

    form = AgingFilterForm(request.GET or None)
    as_of = form.get_as_of()

    try:
        from accounting.models import Invoice
        invoices = Invoice.objects.select_related('customer').filter(
            status__in=['sent', 'partial', 'overdue']
        )
    except Exception:
        invoices = []

    columns = ['Customer', 'Invoice #', 'Invoice Date', 'Due Date', 'Current', '1-30 Days', '31-60 Days', '61-90 Days', '90+ Days', 'Total Balance']
    rows = []
    totals = [Decimal('0')] * 5  # current, 30, 60, 90, 90+

    for inv in invoices:
        balance = inv.total_amount - inv.amount_paid
        if balance <= 0:
            continue
        days = (as_of - inv.due_date).days
        buckets = [Decimal('0')] * 5
        if days <= 0:
            buckets[0] = balance   # current (not yet due)
        elif days <= 30:
            buckets[1] = balance
        elif days <= 60:
            buckets[2] = balance
        elif days <= 90:
            buckets[3] = balance
        else:
            buckets[4] = balance
        for i in range(5):
            totals[i] += buckets[i]
        rows.append([
            inv.customer.full_name if inv.customer else '—',
            inv.invoice_number,
            inv.invoice_date.strftime('%Y-%m-%d'),
            inv.due_date.strftime('%Y-%m-%d'),
            buckets[0], buckets[1], buckets[2], buckets[3], buckets[4],
            balance,
        ])

    summary = {
        'Total Outstanding': sum(totals),
        'Current': totals[0],
        '1-30 Days': totals[1],
        '31-60 Days': totals[2],
        '61-90 Days': totals[3],
        '90+ Days': totals[4],
    }
    return _render_report(request, f'AR Aging Report (As of {as_of})', columns, rows, summary,
                          form, 'ar-aging', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 12. AP Aging
# ─────────────────────────────────────────────────────────────

@login_required
def ap_aging(request):
    if not _can_access(request.user, 'ap-aging'):
        return _deny(request)

    form = AgingFilterForm(request.GET or None)
    as_of = form.get_as_of()

    try:
        from accounting.models import Bill
        bills = Bill.objects.select_related('vendor').filter(
            status__in=['received', 'partial', 'overdue']
        )
    except Exception:
        bills = []

    columns = ['Vendor', 'Bill #', 'Bill Date', 'Due Date', 'Current', '1-30 Days', '31-60 Days', '61-90 Days', '90+ Days', 'Total Balance']
    rows = []
    totals = [Decimal('0')] * 5

    for bill in bills:
        balance = bill.total_amount - bill.amount_paid
        if balance <= 0:
            continue
        days = (as_of - bill.due_date).days
        buckets = [Decimal('0')] * 5
        if days <= 0:
            buckets[0] = balance
        elif days <= 30:
            buckets[1] = balance
        elif days <= 60:
            buckets[2] = balance
        elif days <= 90:
            buckets[3] = balance
        else:
            buckets[4] = balance
        for i in range(5):
            totals[i] += buckets[i]
        rows.append([
            bill.vendor.name if bill.vendor else '—',
            bill.bill_number,
            bill.bill_date.strftime('%Y-%m-%d'),
            bill.due_date.strftime('%Y-%m-%d'),
            buckets[0], buckets[1], buckets[2], buckets[3], buckets[4],
            balance,
        ])

    summary = {
        'Total Outstanding': sum(totals),
        'Current': totals[0],
        '1-30 Days': totals[1],
        '31-60 Days': totals[2],
        '61-90 Days': totals[3],
        '90+ Days': totals[4],
    }
    return _render_report(request, f'AP Aging Report (As of {as_of})', columns, rows, summary,
                          form, 'ap-aging', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 13. Tax Report
# ─────────────────────────────────────────────────────────────

@login_required
def tax_report(request):
    if not _can_access(request.user, 'tax'):
        return _deny(request)

    form = TaxFilterForm(request.GET or None)
    date_from, date_to = form.get_date_range() if form.is_valid() else (
        _today() - timedelta(days=30), _today()
    )
    period = (form.cleaned_data.get('period') or 'month') if form.is_valid() else 'month'
    trunc_fn = {'day': TruncDay, 'month': TruncMonth, 'year': TruncYear}.get(period, TruncMonth)

    try:
        from accounting.models import Invoice, Bill

        inv_data = (
            Invoice.objects.filter(
                status__in=['sent', 'partial', 'paid'],
                invoice_date__gte=date_from,
                invoice_date__lte=date_to,
            )
            .annotate(pg=trunc_fn('invoice_date'))
            .values('pg')
            .annotate(tax_collected=Sum('tax_amount'), invoices=Count('id'))
            .order_by('pg')
        )
        bill_data = (
            Bill.objects.filter(
                status__in=['received', 'partial', 'paid'],
                bill_date__gte=date_from,
                bill_date__lte=date_to,
            )
            .annotate(pg=trunc_fn('bill_date'))
            .values('pg')
            .annotate(tax_paid=Sum('tax_amount'), bills=Count('id'))
            .order_by('pg')
        )

        # Merge by period
        inv_map = {d['pg']: d for d in inv_data}
        bill_map = {d['pg']: d for d in bill_data}
        all_periods = sorted(set(list(inv_map.keys()) + list(bill_map.keys())))

        columns = ['Period', 'Invoices', 'Tax Collected', 'Bills', 'Tax Paid', 'Net Tax Payable']
        rows = []
        total_collected = Decimal('0')
        total_paid = Decimal('0')
        for pg in all_periods:
            inv = inv_map.get(pg, {})
            bil = bill_map.get(pg, {})
            collected = inv.get('tax_collected') or Decimal('0')
            paid = bil.get('tax_paid') or Decimal('0')
            net = collected - paid
            total_collected += collected
            total_paid += paid
            label = pg.strftime('%Y-%m-%d') if pg else '—'
            rows.append([label, inv.get('invoices', 0), collected, bil.get('bills', 0), paid, net])

    except Exception:
        columns = ['Period', 'Invoices', 'Tax Collected', 'Bills', 'Tax Paid', 'Net Tax Payable']
        rows = []
        total_collected = total_paid = Decimal('0')

    summary = {
        'Tax Collected': total_collected,
        'Tax Paid': total_paid,
        'Net Tax Payable': total_collected - total_paid,
    }
    return _render_report(request, 'Tax Report', columns, rows, summary,
                          form, 'tax', request.GET.get('export'))


# ─────────────────────────────────────────────────────────────
# 14. Custom Report Builder
# ─────────────────────────────────────────────────────────────

@login_required
def custom_builder(request):
    if not _can_access(request.user, 'custom'):
        return _deny(request)

    form = CustomReportForm(request.GET or None)
    columns, rows, summary, title = [], [], {}, 'Custom Report'
    has_results = False

    if form.is_valid() and request.GET:
        date_from, date_to = form.get_date_range()
        entity = form.cleaned_data.get('entity', 'sales_orders')
        group_by = form.cleaned_data.get('group_by', 'none')
        title = f'Custom Report — {dict(form.fields["entity"].choices).get(entity, entity)}'
        has_results = True

        if entity == 'sales_orders':
            from sales.models import SalesOrder
            qs = SalesOrder.objects.select_related('customer').filter(
                order_date__gte=date_from, order_date__lte=date_to,
            )
            if group_by == 'status':
                data = qs.values('status').annotate(count=Count('id'), total=Sum('subtotal')).order_by('status')
                columns = ['Status', 'Orders', 'Total Revenue']
                rows = [[d['status'], d['count'], d['total'] or Decimal('0')] for d in data]
            elif group_by == 'month':
                data = qs.annotate(m=TruncMonth('order_date')).values('m').annotate(
                    count=Count('id'), total=Sum('subtotal')).order_by('m')
                columns = ['Month', 'Orders', 'Total Revenue']
                rows = [[d['m'].strftime('%Y-%m'), d['count'], d['total'] or Decimal('0')] for d in data]
            else:
                columns = ['Order #', 'Customer', 'Date', 'Status', 'Subtotal']
                rows = [[o.order_number, o.customer.full_name, o.order_date, o.status, o.subtotal]
                        for o in qs.order_by('-order_date')[:200]]
            summary = {'Total Records': len(rows)}

        elif entity == 'purchase_orders':
            from purchasing.models import PurchaseOrder
            qs = PurchaseOrder.objects.select_related('vendor').filter(
                order_date__gte=date_from, order_date__lte=date_to,
            )
            if group_by == 'status':
                data = qs.values('status').annotate(count=Count('id'), total=Sum('total_amount')).order_by('status')
                columns = ['Status', 'POs', 'Total Spend']
                rows = [[d['status'], d['count'], d['total'] or Decimal('0')] for d in data]
            elif group_by == 'month':
                data = qs.annotate(m=TruncMonth('order_date')).values('m').annotate(
                    count=Count('id'), total=Sum('total_amount')).order_by('m')
                columns = ['Month', 'POs', 'Total Spend']
                rows = [[d['m'].strftime('%Y-%m'), d['count'], d['total'] or Decimal('0')] for d in data]
            else:
                columns = ['PO #', 'Vendor', 'Date', 'Status', 'Total']
                rows = [[p.po_number, p.vendor.name, p.order_date, p.status, p.total_amount]
                        for p in qs.order_by('-order_date')[:200]]
            summary = {'Total Records': len(rows)}

        elif entity == 'products':
            from products.models import Product
            qs = Product.objects.select_related('category', 'brand').filter(active=True)
            if group_by == 'category':
                data = qs.values('category__name').annotate(count=Count('id')).order_by('-count')
                columns = ['Category', 'Product Count']
                rows = [[d['category__name'] or 'Uncategorised', d['count']] for d in data]
            else:
                columns = ['Product', 'SKU', 'Category', 'Price', 'Cost']
                rows = [[p.name, p.sku or p.code, p.category.name if p.category else '—',
                          p.price, p.cost] for p in qs.order_by('name')[:200]]
            summary = {'Total Records': len(rows)}

        elif entity == 'inventory':
            from inventory.models import Stock
            qs = Stock.objects.select_related('product', 'warehouse').annotate(
                val=ExpressionWrapper(F('quantity') * F('cost_price'), output_field=DecimalField())
            )
            if group_by == 'category':
                data = qs.values('product__category__name').annotate(
                    items=Count('id'), qty=Sum('quantity'), value=Sum(F('quantity') * F('cost_price'))
                ).order_by('-value')
                columns = ['Category', 'SKUs', 'Total Qty', 'Total Value']
                rows = [[d['product__category__name'] or '—', d['items'],
                          d['qty'] or 0, d['value'] or Decimal('0')] for d in data]
            else:
                columns = ['Product', 'Warehouse', 'Qty', 'Reorder Level', 'Value']
                rows = [[s.product.name, s.warehouse.name, s.quantity,
                          s.reorder_level, s.val or Decimal('0')] for s in qs.order_by('product__name')[:200]]
            summary = {'Total Records': len(rows)}

    if request.GET.get('export') and has_results:
        return export_report(title, columns, rows, request.GET['export'], summary)

    return render(request, 'reports/custom_builder.html', {
        'form': form,
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
        'has_results': has_results,
        'report_nav': _build_report_nav(request.user),
        'report_key': 'custom',
    })
