from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.models import Country, Region, City
from .models import (
    Vendor, PurchaseOrder, PurchaseOrderLine, 
    PurchaseReceipt, PurchaseReceiptLine
)


class VendorAdminForm(forms.ModelForm):
    confirm_duplicate = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.HiddenInput()
    )
    
    class Meta:
        model = Vendor
        fields = '__all__'
        widgets = {
            'country': forms.Select(attrs={'class': 'country-select'}),
            'region': forms.Select(attrs={'class': 'region-select'}),
            'city': forms.Select(attrs={'class': 'city-select'}),
            'address_line1': forms.TextInput(attrs={'placeholder': '123 Main Street'}),
            'address_line2': forms.TextInput(attrs={'placeholder': 'Suite 100'}),
            'postal_code': forms.TextInput(attrs={'placeholder': '10001'}),
        }
        labels = {
            'address_line1': 'Address Line 1:',
            'address_line2': 'Address Line 2:',
            'country': 'Country:',
            'region': 'Region / State:',
            'city': 'City:',
            'postal_code': 'ZIP / Postal Code:',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        field_order = [
            'name', 'code', 'contact_person', 'email', 'phone', 'mobile', 'website',
            'address_line1', 'address_line2', 'country', 'region', 'city', 'postal_code',
            'tax_number', 'registration_number', 'gst_number',
            'payment_terms', 'credit_days', 'credit_limit', 'opening_balance', 'currency',
            'is_active', 'is_preferred', 'notes'
        ]
        
        existing_fields = [f for f in field_order if f in self.fields]
        if existing_fields:
            self.order_fields(existing_fields)
        
        self.setup_country_field()
        self.setup_region_field()
        self.setup_city_field()
        
        self.original_name = None
        if self.instance and self.instance.pk:
            self.original_name = self.instance.name
    
    def setup_country_field(self):
        if 'country' in self.fields:
            if self.instance and self.instance.pk and self.instance.country:
                self.fields['country'].queryset = Country.objects.all()
            else:
                self.fields['country'].queryset = Country.objects.filter(is_active=True)
            self.fields['country'].help_text = "Select a country first"
    
    def setup_region_field(self):
        if 'region' not in self.fields:
            return
            
        country_id = None
        if self.data.get('country'):
            country_id = self.data.get('country')
        elif self.instance and self.instance.country_id:
            country_id = self.instance.country_id
        
        if country_id:
            self.fields['region'].queryset = Region.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['region'].required = False
            self.fields['region'].widget.attrs.pop('disabled', None)
            self.fields['region'].help_text = "Select a region/state (optional)"
        else:
            self.fields['region'].queryset = Region.objects.none()
            self.fields['region'].required = False
            self.fields['region'].widget.attrs['disabled'] = True
            self.fields['region'].help_text = "Select a country first"
    
    def setup_city_field(self):
        if 'city' not in self.fields:
            return
            
        country_id = None
        region_id = None
        
        if self.data.get('country'):
            country_id = self.data.get('country')
        elif self.instance and self.instance.country_id:
            country_id = self.instance.country_id
        
        if self.data.get('region'):
            region_id = self.data.get('region')
        elif self.instance and self.instance.region_id:
            region_id = self.instance.region_id
        
        if region_id:
            self.fields['city'].queryset = City.objects.filter(
                region_id=region_id,
                is_active=True
            ).order_by('name')
            self.fields['city'].widget.attrs.pop('disabled', None)
            self.fields['city'].help_text = "Select a city"
        elif country_id:
            self.fields['city'].queryset = City.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['city'].widget.attrs.pop('disabled', None)
            self.fields['city'].help_text = "Select a city (all cities in country)"
        else:
            self.fields['city'].queryset = City.objects.none()
            self.fields['city'].required = False
            self.fields['city'].widget.attrs['disabled'] = True
            self.fields['city'].help_text = "Select a country first"
    
    def clean(self):
        cleaned_data = super().clean()
        
        country = cleaned_data.get('country')
        region = cleaned_data.get('region')
        city = cleaned_data.get('city')
        confirm = self.data.get('confirm_duplicate')
        
        if country and region and region.country_id != country.id:
            self.add_error('region', 
                f"Selected region '{region.name}' does not belong to selected country '{country.name}'")
        
        if city:
            if region and city.region_id != region.id:
                self.add_error('city',
                    f"Selected city '{city.name}' does not belong to selected region '{region.name}'")
            elif country and city.country_id != country.id:
                self.add_error('city',
                    f"Selected city '{city.name}' does not belong to selected country '{country.name}'")
        
        name = cleaned_data.get('name')
        if name and not confirm:
            duplicate_exists = Vendor.objects.filter(
                name__iexact=name
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            
            if duplicate_exists:
                self.add_error('name', 
                    ValidationError(
                        'A vendor with this name already exists. Please confirm if you want to create a duplicate.',
                        code='duplicate_name'
                    )
                )
        
        return cleaned_data


class PurchaseOrderLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = [
            'product', 'quantity', 'unit', 'price', 
            'discount_percent', 'tax_rate', 'warehouse', 'section',
            'notes'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'product-select'}),
            'unit': forms.Select(attrs={'class': 'unit-select'}),
            'warehouse': forms.Select(attrs={'class': 'warehouse-select'}),
            'section': forms.Select(attrs={'class': 'section-select'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'discount_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'tax_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Debug: Print available fields
        print(f"PurchaseOrderLineForm fields: {list(self.fields.keys())}")
        
        # Make fields required - check if they exist first
        if 'product' in self.fields:
            self.fields['product'].required = True
        if 'quantity' in self.fields:
            self.fields['quantity'].required = True
        if 'price' in self.fields:
            self.fields['price'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        
        quantity = cleaned_data.get('quantity')
        price = cleaned_data.get('price')
        discount_percent = cleaned_data.get('discount_percent', 0)
        
        if quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than 0')
        
        if price is not None and price < 0:
            self.add_error('price', 'Price cannot be negative')
        
        if discount_percent and discount_percent > 100:
            self.add_error('discount_percent', 'Discount percentage cannot exceed 100%')
        
        return cleaned_data


class PurchaseReceiptLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseReceiptLine
        fields = [
            'order_line', 'product', 'quantity_received', 'quantity_rejected',
            'quality_status', 'batch_number', 'expiry_date', 'manufacturing_date',
            'section', 'notes'
        ]
        widgets = {
            'order_line': forms.Select(attrs={'class': 'order-line-select'}),
            'product': forms.Select(attrs={'class': 'product-select', 'readonly': 'readonly'}),
            'quantity_received': forms.NumberInput(attrs={
                'step': '0.01', 
                'min': '0',
                'class': 'quantity-received-input'
            }),
            'quantity_rejected': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'batch_number': forms.TextInput(attrs={'placeholder': 'Enter batch/lot number'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'manufacturing_date': forms.DateInput(attrs={'type': 'date'}),
            'section': forms.Select(attrs={'class': 'section-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make fields required
        self.fields['order_line'].required = True
        self.fields['product'].required = True
        self.fields['quantity_received'].required = True
        
        # Add max value attribute to quantity_received field
        if self.instance and self.instance.pk:
            if self.instance.order_line:
                max_qty = self.instance.order_line.remaining_quantity
                self.fields['quantity_received'].widget.attrs['max'] = max_qty
                self.fields['quantity_received'].help_text = f"Maximum: {max_qty}"
    
    def clean(self):
        cleaned_data = super().clean()
        
        quantity_received = cleaned_data.get('quantity_received')
        quantity_rejected = cleaned_data.get('quantity_rejected', 0)
        order_line = cleaned_data.get('order_line')
        
        # STEP 1: Validate quantity is positive
        if quantity_received is not None:
            if quantity_received <= 0:
                self.add_error('quantity_received', 
                    'Quantity received must be greater than 0')
        
        # STEP 2: Validate quantity rejected is not negative
        if quantity_rejected and quantity_rejected < 0:
            self.add_error('quantity_rejected', 
                'Quantity rejected cannot be negative')
        
        # STEP 3: Validate rejected doesn't exceed received
        if quantity_received and quantity_rejected and quantity_rejected > quantity_received:
            self.add_error('quantity_rejected', 
                'Quantity rejected cannot exceed quantity received')
        
        # STEP 4: Validate against order line remaining quantity
        if order_line and quantity_received:
            max_allowed = order_line.remaining_quantity
            
            if quantity_received > max_allowed:
                self.add_error('quantity_received', 
                    f'Cannot receive more than remaining quantity. '
                    f'Ordered: {order_line.quantity}, '
                    f'Already received: {order_line.received_quantity}, '
                    f'Remaining: {max_allowed}'
                )
        
        return cleaned_data


class PurchaseOrderFilterForm(forms.Form):
    """Form for filtering purchase orders in list views"""
    STATUS_CHOICES = [('', 'All')] + PurchaseOrder.STATUS_CHOICES
    
    po_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'PO Number'}))
    vendor = forms.ModelChoiceField(required=False, queryset=Vendor.objects.filter(is_active=True))
    status = forms.ChoiceField(required=False, choices=STATUS_CHOICES)
    from_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    to_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    
    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        
        if from_date and to_date and from_date > to_date:
            self.add_error('to_date', 'To date must be after from date')
        
        return cleaned_data


class PurchaseReceiptFilterForm(forms.Form):
    """Form for filtering purchase receipts in list views"""
    RECEIPT_STATUS_CHOICES = [('', 'All')] + PurchaseReceipt.RECEIPT_STATUS
    
    receipt_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Receipt Number'}))
    purchase_order = forms.ModelChoiceField(required=False, queryset=PurchaseOrder.objects.all())
    status = forms.ChoiceField(required=False, choices=RECEIPT_STATUS_CHOICES)
    from_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    to_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    
    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        
        if from_date and to_date and from_date > to_date:
            self.add_error('to_date', 'To date must be after from date')
        
        return cleaned_data


class PurchaseOrderBulkActionForm(forms.Form):
    """Form for bulk actions on purchase orders"""
    ACTION_CHOICES = [
        ('confirm', 'Confirm selected orders'),
        ('cancel', 'Cancel selected orders'),
        ('export_csv', 'Export as CSV'),
        ('export_pdf', 'Export as PDF'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES, required=True)
    selected_ids = forms.CharField(widget=forms.HiddenInput, required=False)
    
    def clean_selected_ids(self):
        data = self.cleaned_data['selected_ids']
        if data:
            try:
                return [int(id) for id in data.split(',') if id]
            except ValueError:
                raise ValidationError("Invalid ID format")
        return []


class VendorFilterForm(forms.Form):
    """Form for filtering vendors in list views"""
    name = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Vendor Name'}))
    code = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Vendor Code'}))
    country = forms.ModelChoiceField(required=False, queryset=Country.objects.filter(is_active=True))
    is_active = forms.NullBooleanField(required=False, widget=forms.Select(choices=[
        ('', 'All'),
        ('true', 'Active'),
        ('false', 'Inactive'),
    ]))
    is_preferred = forms.NullBooleanField(required=False, widget=forms.Select(choices=[
        ('', 'All'),
        ('true', 'Preferred'),
        ('false', 'Regular'),
    ]))


class DateRangeForm(forms.Form):
    """Form for date range selection in reports"""
    from_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'vDateField'})
    )
    to_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'vDateField'})
    )
    report_type = forms.ChoiceField(
        required=False,
        choices=[
            ('summary', 'Summary Report'),
            ('detailed', 'Detailed Report'),
            ('vendor', 'Vendor-wise Report'),
        ]
    )
    
    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        
        if from_date and to_date and from_date > to_date:
            self.add_error('to_date', 'To date must be after from date')
        
        return cleaned_data