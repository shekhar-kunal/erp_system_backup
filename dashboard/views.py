from django.shortcuts import render
from products.models import Product
from inventory.models import Stock
from sales.models import SalesOrderLine
from purchasing.models import PurchaseOrderLine
from django.db.models import Sum, F, DecimalField, ExpressionWrapper


def dashboard_view(request):
    total_products = Product.objects.count()

    low_stock = Stock.objects.filter(quantity__lt=10).count()

    # SALES TOTAL
    sales_total = SalesOrderLine.objects.filter(
        order__status='confirmed'
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F('quantity') * F('price'),
                output_field=DecimalField()
            )
        )
    )['total'] or 0

    # PURCHASE TOTAL
    purchase_total = PurchaseOrderLine.objects.filter(
        order__status='confirmed'
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F('quantity') * F('price'),
                output_field=DecimalField()
            )
        )
    )['total'] or 0

    context = {
        'total_products': total_products,
        'low_stock': low_stock,
        'total_sales': sales_total,
        'total_purchases': purchase_total,
    }

    return render(request, 'dashboard/dashboard.html', context)
