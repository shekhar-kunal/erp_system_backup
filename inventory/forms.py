from django import forms
from django.core.exceptions import ValidationError
from .models import (
    StockBatch, Stock, Warehouse, WarehouseSection,
    StockCount, StockCountLine
)


class StockBatchForm(forms.ModelForm):
    """Form for StockBatch model"""
    class Meta:
        model = StockBatch
        fields = [
            'stock', 'batch_number', 'quantity', 'unit', 'unit_quantity',
            'manufacturing_date', 'expiry_date',
            'supplier', 'supplier_batch', 'quality_status', 'notes', 'is_active'
        ]
        widgets = {
            'manufacturing_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['batch_number'].required = True
        self.fields['quantity'].required = True
        self.fields['stock'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        mfg_date = cleaned_data.get('manufacturing_date')
        exp_date = cleaned_data.get('expiry_date')
        quantity = cleaned_data.get('quantity')
        
        if mfg_date and exp_date and mfg_date > exp_date:
            raise forms.ValidationError("Manufacturing date cannot be after expiry date")
        
        if quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than 0')
        
        return cleaned_data


class BatchReceiveForm(forms.ModelForm):
    class Meta:
        model = StockBatch
        fields = ['stock', 'batch_number', 'quantity', 'unit', 
                  'manufacturing_date', 'expiry_date', 'supplier', 
                  'supplier_batch', 'notes']
        widgets = {
            'manufacturing_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['batch_number'].required = True
        self.fields['quantity'].required = True
        self.fields['stock'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        mfg_date = cleaned_data.get('manufacturing_date')
        exp_date = cleaned_data.get('expiry_date')
        quantity = cleaned_data.get('quantity')
        
        if mfg_date and exp_date and mfg_date > exp_date:
            raise forms.ValidationError("Manufacturing date cannot be after expiry date")
        
        if quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than 0')
        
        return cleaned_data


class ManualMovementForm(forms.Form):
    """Form for manual stock adjustments"""
    MOVEMENT_TYPES = [
        ('IN', 'Add Stock'),
        ('OUT', 'Remove Stock'),
    ]
    
    movement_type = forms.ChoiceField(
        choices=MOVEMENT_TYPES,
        required=True,
        widget=forms.RadioSelect,
        initial='IN'
    )
    quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0.01,
        required=True,
        widget=forms.NumberInput(attrs={'step': '0.01', 'class': 'vIntegerField'}),
        help_text="Enter positive quantity (will be added or removed based on type)"
    )
    source = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Manual Adjustment'}),
        help_text="Source of movement (e.g., Manual Adjustment, Return, etc.)"
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g., REF-001'}),
        help_text="Optional reference number"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'})
    )

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity <= 0:
            raise ValidationError("Quantity must be greater than 0")
        return quantity


class StockFilterForm(forms.Form):
    """Form for filtering stock in list views"""
    warehouse = forms.ModelChoiceField(
        required=False,
        queryset=Warehouse.objects.filter(is_active=True),
        empty_label="All Warehouses",
        widget=forms.Select(attrs={'class': 'filter-select'})
    )
    product = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Product name or SKU', 'class': 'filter-input'})
    )
    low_stock_only = forms.BooleanField(
        required=False,
        label="Low stock only",
        widget=forms.CheckboxInput(attrs={'class': 'filter-checkbox'})
    )
    frozen_only = forms.BooleanField(
        required=False,
        label="Frozen only",
        widget=forms.CheckboxInput(attrs={'class': 'filter-checkbox'})
    )
    show_zero_stock = forms.BooleanField(
        required=False,
        label="Show zero stock",
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'filter-checkbox'})
    )


class StockBatchFilterForm(forms.Form):
    """Form for filtering stock batches"""
    QUALITY_STATUS_CHOICES = [
        ('', 'All'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('quarantine', 'Quarantine'),
        ('pending', 'Pending'),
    ]
    
    quality_status = forms.ChoiceField(
        required=False,
        choices=QUALITY_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'filter-select'})
    )
    is_active = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive'),
        ], attrs={'class': 'filter-select'})
    )
    expiry_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'filter-date'})
    )
    expiry_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'filter-date'})
    )
    supplier = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Supplier name', 'class': 'filter-input'})
    )


class StockCountForm(forms.ModelForm):
    """Form for stock count creation"""
    class Meta:
        model = StockCount
        fields = ['name', 'warehouse', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'vTextField', 'placeholder': 'e.g., Monthly Count - March 2026'}),
            'warehouse': forms.Select(attrs={'class': 'warehouse-select'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes...'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['warehouse'].required = True


class StockCountLineForm(forms.ModelForm):
    """Form for stock count line items"""
    class Meta:
        model = StockCountLine
        fields = ['product', 'expected_quantity', 'counted_quantity', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'product-select'}),
            'expected_quantity': forms.NumberInput(attrs={'step': '0.01', 'readonly': 'readonly'}),
            'counted_quantity': forms.NumberInput(attrs={'step': '0.01', 'class': 'count-input'}),
            'notes': forms.TextInput(attrs={'placeholder': 'Optional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].required = True
        self.fields['expected_quantity'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        expected = cleaned_data.get('expected_quantity')
        counted = cleaned_data.get('counted_quantity')
        
        if counted is not None and counted < 0:
            self.add_error('counted_quantity', 'Counted quantity cannot be negative')
        
        return cleaned_data


class WarehouseSectionForm(forms.ModelForm):
    """Form for warehouse sections"""
    class Meta:
        model = WarehouseSection
        fields = ['warehouse', 'zone', 'aisle', 'rack', 'bin', 
                  'barcode', 'max_capacity', 'description', 'is_active']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'warehouse-select'}),
            'zone': forms.TextInput(attrs={'placeholder': 'e.g., A'}),
            'aisle': forms.TextInput(attrs={'placeholder': 'e.g., 01'}),
            'rack': forms.TextInput(attrs={'placeholder': 'e.g., 02'}),
            'bin': forms.TextInput(attrs={'placeholder': 'e.g., 03'}),
            'barcode': forms.TextInput(attrs={'placeholder': 'Auto-generated if blank'}),
            'max_capacity': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        zone = cleaned_data.get('zone')
        aisle = cleaned_data.get('aisle')
        rack = cleaned_data.get('rack')
        bin_code = cleaned_data.get('bin')
        
        # Check for duplicate location
        if warehouse and zone and aisle and rack and bin_code:
            exists = WarehouseSection.objects.filter(
                warehouse=warehouse,
                zone=zone,
                aisle=aisle,
                rack=rack,
                bin=bin_code
            ).exclude(pk=self.instance.pk if self.instance.pk else None).exists()
            
            if exists:
                raise ValidationError(
                    f"Section {zone}-{aisle}-{rack}-{bin_code} already exists in this warehouse"
                )
        
        return cleaned_data


class BulkStockUpdateForm(forms.Form):
    """Form for bulk updating stock levels"""
    ACTION_CHOICES = [
        ('set', 'Set to value'),
        ('increase', 'Increase by'),
        ('decrease', 'Decrease by'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'action-select'})
    )
    value = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={'step': '0.01', 'class': 'value-input'})
    )
    reason = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Reason for bulk update'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes'})
    )
    
    def clean_value(self):
        value = self.cleaned_data.get('value')
        if value < 0:
            raise ValidationError("Value cannot be negative")
        return value


class TransferStockForm(forms.Form):
    """Form for transferring stock between locations"""
    destination_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        required=True,
        widget=forms.Select(attrs={'class': 'warehouse-select'})
    )
    destination_section = forms.ModelChoiceField(
        queryset=WarehouseSection.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'section-select'})
    )
    quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0.01,
        required=True,
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g., TRANS-001'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Transfer notes'})
    )
    
    def __init__(self, *args, **kwargs):
        source_warehouse = kwargs.pop('source_warehouse', None)
        super().__init__(*args, **kwargs)
        
        if source_warehouse:
            self.fields['destination_section'].queryset = WarehouseSection.objects.filter(
                warehouse=source_warehouse,
                is_active=True
            )
    
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity <= 0:
            raise ValidationError("Quantity must be positive")
        return quantity