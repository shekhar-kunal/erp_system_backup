from django import forms
from django.core.exceptions import ValidationError
from core.models import Country, Region, City
from .models import Customer


class CustomerAdminForm(forms.ModelForm):
    # Add a field to track if user confirmed saving a duplicate
    confirm_duplicate = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.HiddenInput()
    )
    
    class Meta:
        model = Customer
        fields = '__all__'
        widgets = {
            'billing_country': forms.Select(attrs={'class': 'country-select billing-country'}),
            'billing_region': forms.Select(attrs={'class': 'region-select billing-region'}),
            'billing_city': forms.Select(attrs={'class': 'city-select billing-city'}),
            'shipping_country': forms.Select(attrs={'class': 'country-select shipping-country'}),
            'shipping_region': forms.Select(attrs={'class': 'region-select shipping-region'}),
            'shipping_city': forms.Select(attrs={'class': 'city-select shipping-city'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get the current customer type
        customer_type = None
        if self.instance and self.instance.pk:
            customer_type = self.instance.customer_type
        elif self.data.get('customer_type'):
            customer_type = self.data.get('customer_type')
        
        # Make all fields not required initially
        self.fields['first_name'].required = False
        self.fields['last_name'].required = False
        self.fields['company_name'].required = False
        
        # Adjust required fields and disable irrelevant fields based on customer type
        if customer_type == Customer.CustomerType.INDIVIDUAL:
            self.fields['first_name'].required = True
            self.fields['last_name'].required = True
            
            # Disable business fields for individual customers
            business_fields = ['company_name', 'company_registration', 'business_type', 'website']
            for field_name in business_fields:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs['disabled'] = True
                    self.fields[field_name].help_text = "Not applicable for individual customers"
                    
        elif customer_type == Customer.CustomerType.BUSINESS:
            self.fields['company_name'].required = True
            
            # Disable individual fields for business customers
            individual_fields = ['first_name', 'last_name', 'date_of_birth']
            for field_name in individual_fields:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs['disabled'] = True
                    self.fields[field_name].help_text = "Not required for business customers"
        
        # Order fields in a logical sequence
        field_order = [
            'customer_type',
            # Individual fields
            'first_name', 'last_name', 'full_name', 'date_of_birth',
            # Business fields
            'company_name', 'company_registration', 'tax_number', 'business_type', 'website',
            # Contact
            'email', 'phone', 'mobile', 'fax',
            # Billing Address
            'billing_address_line1', 'billing_address_line2',
            'billing_country', 'billing_region', 'billing_city', 'billing_postal_code',
            'same_as_billing',
            # Shipping Address
            'shipping_address_line1', 'shipping_address_line2',
            'shipping_country', 'shipping_region', 'shipping_city', 'shipping_postal_code',
            # Business Transactions
            'payment_type', 'credit_limit', 'credit_days', 'customer_code',
            'default_currency', 'price_list', 'discount_percent',
            # Sales & Marketing
            'preferred_language', 'assigned_salesperson', 'source',
            # Status & Loyalty
            'is_active', 'is_vip', 'position', 'loyalty_points',
            'preferred_payment_method', 'last_order_date', 'notes'
        ]
        
        # Only apply order if all fields exist
        existing_fields = [f for f in field_order if f in self.fields]
        if existing_fields:
            self.order_fields(existing_fields)
        
        # Setup billing address fields
        self.setup_billing_country_field()
        self.setup_billing_region_field()
        self.setup_billing_city_field()
        
        # Setup shipping address fields
        self.setup_shipping_country_field()
        self.setup_shipping_region_field()
        self.setup_shipping_city_field()
        
        # Store the original email for comparison
        self.original_email = None
        if self.instance and self.instance.pk:
            self.original_email = self.instance.email
    
    # ============= BILLING ADDRESS FIELDS =============
    
    def setup_billing_country_field(self):
        """Setup billing country queryset"""
        if 'billing_country' in self.fields:
            if self.instance and self.instance.pk and self.instance.billing_country:
                self.fields['billing_country'].queryset = Country.objects.all()
            else:
                self.fields['billing_country'].queryset = Country.objects.filter(is_active=True)
            self.fields['billing_country'].label = "Country"
            self.fields['billing_country'].help_text = "Select a country first"
    
    def setup_billing_region_field(self):
        """Setup dependent dropdown for billing region"""
        if 'billing_region' not in self.fields:
            return
            
        country_id = None
        
        if self.data.get('billing_country'):
            country_id = self.data.get('billing_country')
        elif self.instance and self.instance.billing_country_id:
            country_id = self.instance.billing_country_id
        
        if country_id:
            self.fields['billing_region'].queryset = Region.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['billing_region'].required = False
            self.fields['billing_region'].widget.attrs['disabled'] = False
            self.fields['billing_region'].label = "Region / State"
            self.fields['billing_region'].help_text = "Select a region/state (optional)"
        else:
            self.fields['billing_region'].queryset = Region.objects.none()
            self.fields['billing_region'].required = False
            self.fields['billing_region'].widget.attrs['disabled'] = True
            self.fields['billing_region'].label = "Region / State (select country first)"
    
    def setup_billing_city_field(self):
        """Setup dependent dropdown for billing city"""
        if 'billing_city' not in self.fields:
            return
            
        country_id = None
        region_id = None
        
        if self.data.get('billing_country'):
            country_id = self.data.get('billing_country')
        elif self.instance and self.instance.billing_country_id:
            country_id = self.instance.billing_country_id
        
        if self.data.get('billing_region'):
            region_id = self.data.get('billing_region')
        elif self.instance and self.instance.billing_region_id:
            region_id = self.instance.billing_region_id
        
        if region_id:
            self.fields['billing_city'].queryset = City.objects.filter(
                region_id=region_id,
                is_active=True
            ).order_by('name')
            self.fields['billing_city'].widget.attrs['disabled'] = False
            self.fields['billing_city'].label = "City"
            self.fields['billing_city'].help_text = "Select a city"
        elif country_id:
            self.fields['billing_city'].queryset = City.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['billing_city'].widget.attrs['disabled'] = False
            self.fields['billing_city'].label = "City"
            self.fields['billing_city'].help_text = "Select a city (all cities in country)"
        else:
            self.fields['billing_city'].queryset = City.objects.none()
            self.fields['billing_city'].widget.attrs['disabled'] = True
            self.fields['billing_city'].label = "City (select country first)"
        
        self.fields['billing_city'].required = False
    
    # ============= SHIPPING ADDRESS FIELDS =============
    
    def setup_shipping_country_field(self):
        """Setup shipping country queryset"""
        if 'shipping_country' in self.fields:
            if self.instance and self.instance.pk and self.instance.shipping_country:
                self.fields['shipping_country'].queryset = Country.objects.all()
            else:
                self.fields['shipping_country'].queryset = Country.objects.filter(is_active=True)
            self.fields['shipping_country'].label = "Country"
            self.fields['shipping_country'].help_text = "Select a country first"
    
    def setup_shipping_region_field(self):
        """Setup dependent dropdown for shipping region"""
        if 'shipping_region' not in self.fields:
            return
            
        country_id = None
        
        if self.data.get('shipping_country'):
            country_id = self.data.get('shipping_country')
        elif self.instance and self.instance.shipping_country_id:
            country_id = self.instance.shipping_country_id
        
        if country_id:
            self.fields['shipping_region'].queryset = Region.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['shipping_region'].required = False
            self.fields['shipping_region'].widget.attrs['disabled'] = False
            self.fields['shipping_region'].label = "Region / State"
            self.fields['shipping_region'].help_text = "Select a region/state (optional)"
        else:
            self.fields['shipping_region'].queryset = Region.objects.none()
            self.fields['shipping_region'].required = False
            self.fields['shipping_region'].widget.attrs['disabled'] = True
            self.fields['shipping_region'].label = "Region / State (select country first)"
    
    def setup_shipping_city_field(self):
        """Setup dependent dropdown for shipping city"""
        if 'shipping_city' not in self.fields:
            return
            
        country_id = None
        region_id = None
        
        if self.data.get('shipping_country'):
            country_id = self.data.get('shipping_country')
        elif self.instance and self.instance.shipping_country_id:
            country_id = self.instance.shipping_country_id
        
        if self.data.get('shipping_region'):
            region_id = self.data.get('shipping_region')
        elif self.instance and self.instance.shipping_region_id:
            region_id = self.instance.shipping_region_id
        
        if region_id:
            self.fields['shipping_city'].queryset = City.objects.filter(
                region_id=region_id,
                is_active=True
            ).order_by('name')
            self.fields['shipping_city'].widget.attrs['disabled'] = False
            self.fields['shipping_city'].label = "City"
            self.fields['shipping_city'].help_text = "Select a city"
        elif country_id:
            self.fields['shipping_city'].queryset = City.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
            self.fields['shipping_city'].widget.attrs['disabled'] = False
            self.fields['shipping_city'].label = "City"
            self.fields['shipping_city'].help_text = "Select a city (all cities in country)"
        else:
            self.fields['shipping_city'].queryset = City.objects.none()
            self.fields['shipping_city'].widget.attrs['disabled'] = True
            self.fields['shipping_city'].label = "City (select country first)"
        
        self.fields['shipping_city'].required = False
    
    # ============= CLEAN METHODS =============
    
    def clean(self):
        cleaned_data = super().clean()
        
        customer_type = cleaned_data.get('customer_type')
        
        # Validate required fields based on customer type
        if customer_type == Customer.CustomerType.INDIVIDUAL:
            if not cleaned_data.get('first_name'):
                self.add_error('first_name', 'First name is required for individual customers.')
            if not cleaned_data.get('last_name'):
                self.add_error('last_name', 'Last name is required for individual customers.')
        elif customer_type == Customer.CustomerType.BUSINESS:
            if not cleaned_data.get('company_name'):
                self.add_error('company_name', 'Company name is required for business customers.')
        
        # Validate billing address
        self.clean_billing_address(cleaned_data)
        
        # Validate shipping address
        self.clean_shipping_address(cleaned_data)
        
        # Handle "same as billing" logic
        if cleaned_data.get('same_as_billing'):
            self.copy_billing_to_shipping(cleaned_data)
        
        # Check for duplicate email
        email = cleaned_data.get('email')
        confirm = cleaned_data.get('confirm_duplicate')
        
        if email:
            duplicate_exists = Customer.objects.filter(
                email__iexact=email
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            
            if duplicate_exists and not confirm:
                self.add_error('email',
                    ValidationError(
                        'A customer with this email already exists. Please confirm if you want to create a duplicate.',
                        code='duplicate_email'
                    )
                )
        
        return cleaned_data
    
    def clean_billing_address(self, cleaned_data):
        """Validate billing address fields"""
        country = cleaned_data.get('billing_country')
        region = cleaned_data.get('billing_region')
        city = cleaned_data.get('billing_city')
        
        if country and region and region.country != country:
            self.add_error('billing_region', 
                f"Selected region '{region.name}' does not belong to selected country '{country.name}'")
        
        if city:
            if region and city.region != region:
                self.add_error('billing_city',
                    f"Selected city '{city.name}' does not belong to selected region '{region.name}'")
            elif country and city.country != country:
                self.add_error('billing_city',
                    f"Selected city '{city.name}' does not belong to selected country '{country.name}'")
    
    def clean_shipping_address(self, cleaned_data):
        """Validate shipping address fields"""
        country = cleaned_data.get('shipping_country')
        region = cleaned_data.get('shipping_region')
        city = cleaned_data.get('shipping_city')
        
        if country and region and region.country != country:
            self.add_error('shipping_region', 
                f"Selected region '{region.name}' does not belong to selected country '{country.name}'")
        
        if city:
            if region and city.region != region:
                self.add_error('shipping_city',
                    f"Selected city '{city.name}' does not belong to selected region '{region.name}'")
            elif country and city.country != country:
                self.add_error('shipping_city',
                    f"Selected city '{city.name}' does not belong to selected country '{country.name}'")
    
    def copy_billing_to_shipping(self, cleaned_data):
        """Copy billing address to shipping address"""
        cleaned_data['shipping_address_line1'] = cleaned_data.get('billing_address_line1')
        cleaned_data['shipping_address_line2'] = cleaned_data.get('billing_address_line2')
        cleaned_data['shipping_postal_code'] = cleaned_data.get('billing_postal_code')
        cleaned_data['shipping_country'] = cleaned_data.get('billing_country')
        cleaned_data['shipping_region'] = cleaned_data.get('billing_region')
        cleaned_data['shipping_city'] = cleaned_data.get('billing_city')
    
    # Override mixin methods
    def get_country_field_name(self):
        return 'billing_country'
    
    def get_city_field_name(self):
        return 'billing_city'