"""Filter forms for the Reports & Analytics app."""
from datetime import timedelta

from django import forms
from django.utils import timezone

from inventory.models import Warehouse
from products.models import ProductCategory
from purchasing.models import PurchaseOrder, Vendor
from sales.models import Customer, SalesOrder


def _today():
    return timezone.now().date()


def _thirty_ago():
    return _today() - timedelta(days=30)


class DateInput(forms.DateInput):
    input_type = 'date'


class DateRangeForm(forms.Form):
    date_from = forms.DateField(required=False, widget=DateInput())
    date_to = forms.DateField(required=False, widget=DateInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data.get('date_from'):
            self.fields['date_from'].initial = _thirty_ago()
        if not self.data.get('date_to'):
            self.fields['date_to'].initial = _today()

    def get_date_range(self):
        """Return (date_from, date_to) with sensible defaults."""
        d_from = self.cleaned_data.get('date_from') if self.is_valid() else None
        d_to = self.cleaned_data.get('date_to') if self.is_valid() else None
        return d_from or _thirty_ago(), d_to or _today()


class SalesFilterForm(DateRangeForm):
    PERIOD_CHOICES = [('day', 'Daily'), ('month', 'Monthly'), ('year', 'Yearly')]
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='month')
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        empty_label='All Customers', required=False,
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(SalesOrder.STATUS_CHOICES),
        required=False,
    )


class PurchaseFilterForm(DateRangeForm):
    PERIOD_CHOICES = [('day', 'Daily'), ('month', 'Monthly'), ('year', 'Yearly')]
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='month')
    vendor = forms.ModelChoiceField(
        queryset=Vendor.objects.all(),
        empty_label='All Vendors', required=False,
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(PurchaseOrder.STATUS_CHOICES),
        required=False,
    )


class InventoryFilterForm(forms.Form):
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all(),
        empty_label='All Warehouses', required=False,
    )
    category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.all(),
        empty_label='All Categories', required=False,
    )


class MovementFilterForm(DateRangeForm):
    MOVEMENT_CHOICES = [
        ('', 'All Types'), ('IN', 'IN'), ('OUT', 'OUT'),
        ('TRANSFER_IN', 'Transfer In'), ('TRANSFER_OUT', 'Transfer Out'),
        ('ADJUSTMENT', 'Adjustment'), ('RETURN', 'Return'),
        ('DAMAGE', 'Damage'), ('COUNT', 'Count'),
    ]
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all(),
        empty_label='All Warehouses', required=False,
    )
    movement_type = forms.ChoiceField(choices=MOVEMENT_CHOICES, required=False)


class ProfitFilterForm(DateRangeForm):
    GROUP_CHOICES = [('product', 'By Product'), ('category', 'By Category')]
    group_by = forms.ChoiceField(choices=GROUP_CHOICES, required=False, initial='product')


class AgingFilterForm(forms.Form):
    as_of = forms.DateField(required=False, widget=DateInput(), label='As of Date')

    def get_as_of(self):
        if self.is_valid():
            return self.cleaned_data.get('as_of') or _today()
        return _today()


class WarehouseFilterForm(forms.Form):
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all(),
        empty_label='All Warehouses', required=False,
    )


class CustomerSalesFilterForm(DateRangeForm):
    pass


class SupplierFilterForm(DateRangeForm):
    pass


class TopProductsFilterForm(DateRangeForm):
    category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.all(),
        empty_label='All Categories', required=False,
    )


class TaxFilterForm(DateRangeForm):
    PERIOD_CHOICES = [('day', 'Daily'), ('month', 'Monthly'), ('year', 'Yearly')]
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='month')


class CustomReportForm(DateRangeForm):
    ENTITY_CHOICES = [
        ('sales_orders', 'Sales Orders'),
        ('purchase_orders', 'Purchase Orders'),
        ('products', 'Products'),
        ('inventory', 'Inventory Stock'),
    ]
    GROUP_CHOICES = [
        ('none', 'No Grouping'),
        ('status', 'By Status'),
        ('month', 'By Month'),
        ('category', 'By Category'),
    ]
    entity = forms.ChoiceField(choices=ENTITY_CHOICES, initial='sales_orders')
    group_by = forms.ChoiceField(choices=GROUP_CHOICES, required=False, initial='none')
