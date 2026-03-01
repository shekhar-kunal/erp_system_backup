from django.db import models, transaction
from django.db.models import Sum, F
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import date, timedelta, datetime
from products.models import Product
from inventory.models import Stock, Warehouse, WarehouseSection
from core.models import Country, City, Region
from django.contrib.auth import get_user_model


User = get_user_model()

# sales/models.py - Add at the top after imports

# sales/models.py - Complete SalesSettings Model

class SalesSettings(models.Model):
    """Global sales settings with feature toggles"""
    
    # ============================================
    # FEATURE TOGGLES - All features can be enabled/disabled
    # ============================================
    
    # Core Features
    enable_quotations = models.BooleanField(
        default=True,
        help_text="Enable quotation management",
        verbose_name="Enable Quotations"
    )
    enable_sales_orders = models.BooleanField(
        default=True,
        help_text="Enable sales orders",
        verbose_name="Enable Sales Orders"
    )
    enable_invoicing = models.BooleanField(
        default=True,
        help_text="Enable invoice generation",
        verbose_name="Enable Invoicing"
    )
    
    # Advanced Features
    enable_order_approval = models.BooleanField(
        default=False,
        help_text="Require approval for sales orders",
        verbose_name="Enable Order Approval"
    )
    enable_delivery_notes = models.BooleanField(
        default=False,
        help_text="Generate delivery notes",
        verbose_name="Enable Delivery Notes"
    )
    enable_sales_returns = models.BooleanField(
        default=False,
        help_text="Handle sales returns/RMA",
        verbose_name="Enable Sales Returns"
    )
    enable_backorders = models.BooleanField(
        default=False,
        help_text="Allow backorders when stock insufficient",
        verbose_name="Enable Backorders"
    )
    enable_credit_limit = models.BooleanField(
        default=True,
        help_text="Enforce customer credit limits",
        verbose_name="Enable Credit Limit"
    )
    
    # Pricing & Discounts
    enable_discounts = models.BooleanField(
        default=True,
        help_text="Enable discount management",
        verbose_name="Enable Discounts"
    )
    enable_tax_calculation = models.BooleanField(
        default=True,
        help_text="Enable tax calculation",
        verbose_name="Enable Tax Calculation"
    )
    enable_profit_tracking = models.BooleanField(
        default=False,
        help_text="Track profit margins",
        verbose_name="Enable Profit Tracking"
    )
    
    # Configuration
    require_approval_for_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=10000.00,
        help_text="Orders above this amount require approval",
        verbose_name="Approval Threshold"
    )
    auto_confirm_approved_orders = models.BooleanField(
        default=True,
        help_text="Automatically confirm orders after approval",
        verbose_name="Auto-confirm Approved Orders"
    )
    default_tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Default tax rate percentage",
        verbose_name="Default Tax Rate (%)"
    )
    quotation_valid_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days quotations are valid",
        verbose_name="Quotation Validity (Days)"
    )
    
    # Numbering Prefixes
    quotation_prefix = models.CharField(
        max_length=10,
        default='Q-',
        help_text="Prefix for quotation numbers",
        verbose_name="Quotation Prefix"
    )
    order_prefix = models.CharField(
        max_length=10,
        default='SO-',
        help_text="Prefix for sales order numbers",
        verbose_name="Order Prefix"
    )
    invoice_prefix = models.CharField(
        max_length=10,
        default='INV-',
        help_text="Prefix for invoice numbers",
        verbose_name="Invoice Prefix"
    )
    delivery_note_prefix = models.CharField(
        max_length=10,
        default='DN-',
        help_text="Prefix for delivery notes",
        verbose_name="Delivery Note Prefix"
    )
    return_prefix = models.CharField(
        max_length=10,
        default='RMA-',
        help_text="Prefix for return numbers",
        verbose_name="Return Prefix"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Sales Settings"
        verbose_name_plural = "Sales Settings"
    
    def __str__(self):
        return "Sales Settings"
    
    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings

class TaxRate(models.Model):
    """Tax rates for different jurisdictions"""
    
    TAX_TYPE_CHOICES = [
        ('sales', 'Sales Tax'),
        ('vat', 'VAT'),
        ('gst', 'GST'),
        ('custom', 'Custom Duty'),
    ]
    
    name = models.CharField(max_length=100)
    rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        help_text="Percentage (e.g., 20.00 for 20%)"
    )
    tax_type = models.CharField(
        max_length=20, 
        choices=TAX_TYPE_CHOICES, 
        default='sales'
    )
    is_active = models.BooleanField(default=True)
    
    # Applicability
    applies_to_countries = models.ManyToManyField(
        'core.Country', 
        blank=True,
        related_name='tax_rates'
    )
    applies_to_regions = models.ManyToManyField(
        'core.Region', 
        blank=True,
        related_name='tax_rates'
    )
    
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['tax_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.rate}%)"
    
    def applies_to_customer(self, customer):
        """Check if this tax rate applies to a customer"""
        if not self.is_active:
            return False
        
        # Check country
        if customer.billing_country:
            if self.applies_to_countries.filter(id=customer.billing_country.id).exists():
                return True
        
        # Check region/state
        if customer.billing_region:
            if self.applies_to_regions.filter(id=customer.billing_region.id).exists():
                return True
        
        return False

class Customer(models.Model):
    class CustomerType(models.TextChoices):
        INDIVIDUAL = 'individual', 'Individual Consumer'
        BUSINESS = 'business', 'Business / Trader'

    class PaymentType(models.TextChoices):
        PAY_NOW = 'pay_now', 'Pay Now'
        CREDIT = 'credit', 'Credit'

    class CurrencyChoices(models.TextChoices):
        USD = 'USD', 'US Dollar'
        EUR = 'EUR', 'Euro'
        GBP = 'GBP', 'British Pound'
        AED = 'AED', 'UAE Dirham'
        INR = 'INR', 'Indian Rupee'
        PKR = 'PKR', 'Pakistani Rupee'

    # ============================================
    # PRICING TIER FIELDS
    # ============================================
    PRICING_TIER_CHOICES = [
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
        ('distributor', 'Distributor'),
        ('special', 'Special'),
    ]
    
    pricing_tier = models.CharField(
        max_length=20,
        choices=PRICING_TIER_CHOICES,
        default='retail',
        verbose_name="Pricing Tier",
        help_text="Determines which price list applies to this customer"
    )
    
    # Override price list (optional - for customers with custom pricing)
    custom_price_list = models.ForeignKey(
        'products.PriceList',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Custom Price List",
        help_text="Override the default pricing tier with a specific price list"
    )
    
    # Custom discount percentage (optional)
    custom_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Custom Discount %",
        help_text="Custom discount percentage (overrides price list)"
    )

    # ============= CUSTOMER TYPE =============
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.INDIVIDUAL,
        verbose_name="Customer Type"
    )

    # ============= INDIVIDUAL FIELDS =============
    first_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="First Name",
        help_text="Required for individual customers"
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Last Name",
        help_text="Required for individual customers"
    )
    full_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Full Name"
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date of Birth"
    )

    # ============= BUSINESS FIELDS =============
    company_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Company Name",
        help_text="Required for business customers"
    )
    company_registration = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Company Registration Number"
    )
    tax_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Tax / VAT Number"
    )
    business_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Business Type",
        help_text="e.g., Retailer, Wholesaler, Distributor"
    )
    website = models.URLField(
        blank=True,
        verbose_name="Website"
    )

    # ============= CONTACT INFORMATION =============
    email = models.EmailField(
        unique=True,
        verbose_name="Email Address"
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Phone Number"
    )
    mobile = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Mobile Number"
    )
    fax = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Fax Number"
    )

    # ============= ADDRESS FIELDS =============
    # Billing Address
    billing_address_line1 = models.CharField(
        max_length=255,
        verbose_name="Address Line 1"
    )
    billing_address_line2 = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Address Line 2"
    )
    billing_country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name='customer_billing_countries',
        verbose_name="Country"
    )
    billing_region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name='customer_billing_regions',
        verbose_name="Region / State",
        null=True,
        blank=True
    )
    billing_city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name='customer_billing_cities',
        verbose_name="City"
    )
    billing_postal_code = models.CharField(
        max_length=20,
        verbose_name="ZIP / Postal Code"
    )

    same_as_billing = models.BooleanField(
        default=False,
        verbose_name="Same as Billing",
        help_text="If checked, shipping address will copy billing address automatically."
    )

    # Shipping Address
    shipping_address_line1 = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Address Line 1"
    )
    shipping_address_line2 = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Address Line 2"
    )
    shipping_country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name='customer_shipping_countries',
        verbose_name="Country",
        null=True,
        blank=True
    )
    shipping_region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name='customer_shipping_regions',
        verbose_name="Region / State",
        null=True,
        blank=True
    )
    shipping_city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name='customer_shipping_cities',
        verbose_name="City",
        null=True,
        blank=True
    )
    shipping_postal_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="ZIP / Postal Code"
    )

    # ============= BUSINESS TRANSACTIONS =============
    payment_type = models.CharField(
        max_length=20,
        choices=PaymentType.choices,
        default=PaymentType.PAY_NOW,
        verbose_name="Payment Type"
    )
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Credit Limit"
    )
    credit_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Credit Days",
        help_text="Number of days allowed for payment"
    )
    customer_code = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        verbose_name="Customer Code"
    )
    default_currency = models.CharField(
        max_length=5,
        choices=CurrencyChoices.choices,
        default=CurrencyChoices.USD,
        verbose_name="Default Currency"
    )
    price_list = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Price List",
        help_text="e.g., Retail, Wholesale, Distributor"
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Default Discount %"
    )

    # ============= SALES & MARKETING =============
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Preferred Language"
    )
    assigned_salesperson = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers',
        verbose_name="Assigned Salesperson"
    )
    source = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Lead Source",
        help_text="e.g., Website, Referral, Walk-in"
    )

    # ============= ACCOUNT & STATUS =============
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )
    is_vip = models.BooleanField(
        default=False,
        verbose_name="VIP Customer"
    )
    position = models.IntegerField(
        default=0,
        verbose_name="Display Position"
    )

    # ============= LOYALTY & ACTIVITY =============
    loyalty_points = models.IntegerField(
        default=0,
        verbose_name="Loyalty Points"
    )
    preferred_payment_method = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Preferred Payment Method"
    )
    last_order_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Last Order Date"
    )
    total_orders_count = models.IntegerField(
        default=0,
        verbose_name="Total Orders Count"
    )
    average_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Average Order Value"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notes"
    )

    # ============= AUDIT FIELDS =============
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_customers',
        verbose_name="Created By"
    )

    class Meta:
        ordering = ['position', 'full_name', 'company_name']
        verbose_name_plural = "Customers"
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['customer_code']),
            models.Index(fields=['customer_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['company_name']),
        ]

    def __str__(self):
        if self.customer_type == self.CustomerType.BUSINESS and self.company_name:
            return f"{self.company_name} ({self.customer_code or 'No Code'})"
        return self.full_name or f"{self.first_name} {self.last_name}"

    def clean(self):
        # Validate based on customer type
        if self.customer_type == self.CustomerType.INDIVIDUAL:
            if not self.first_name or not self.last_name:
                raise ValidationError({
                    'first_name': _("First name and last name are required for individual customers."),
                    'last_name': _("First name and last name are required for individual customers.")
                })
        elif self.customer_type == self.CustomerType.BUSINESS:
            if not self.company_name:
                raise ValidationError({
                    'company_name': _("Company name is required for business customers.")
                })

        # Validate credit limit for credit customers
        if self.payment_type == self.PaymentType.CREDIT and self.credit_limit <= 0:
            raise ValidationError({
                'credit_limit': _("Credit limit must be greater than 0 for credit customers.")
            })

    def save(self, *args, **kwargs):
        # Auto-generate full name for individuals
        if self.customer_type == self.CustomerType.INDIVIDUAL:
            if not self.full_name:
                self.full_name = f"{self.first_name} {self.last_name}".strip()

        # Copy billing address if same_as_billing is True
        if self.same_as_billing:
            self.shipping_address_line1 = self.billing_address_line1
            self.shipping_address_line2 = self.billing_address_line2
            self.shipping_country = self.billing_country
            self.shipping_region = self.billing_region
            self.shipping_city = self.billing_city
            self.shipping_postal_code = self.billing_postal_code

        # Auto-generate customer code if not provided
        if not self.customer_code:
            prefix = "IND" if self.customer_type == self.CustomerType.INDIVIDUAL else "BUS"
            last_customer = Customer.objects.filter(
                customer_code__startswith=prefix
            ).order_by('-id').first()
            
            if last_customer and last_customer.customer_code:
                try:
                    last_num = int(last_customer.customer_code.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.customer_code = f"{prefix}-{last_num + 1:04d}"

        self.full_clean()
        super().save(*args, **kwargs)

    # ============================================
    # FEATURE-AWARE METHODS
    # ============================================
    
    def check_credit_limit(self, order_amount):
        """Check credit limit (only if feature enabled)"""
        settings = SalesSettings.get_settings()
        
        if not settings.enable_credit_limit:
            return True, "Credit limit checking disabled"
        
        if self.payment_type != self.PaymentType.CREDIT:
            return True, "Not a credit customer"
        
        current_due = self.total_due
        if current_due + order_amount > self.credit_limit:
            return False, f"Credit limit exceeded. Limit: {self.credit_limit}, Current due: {current_due}, Order: {order_amount}"
        
        return True, "Credit limit OK"
    
    def get_applicable_tax_rate(self):
        """Get tax rate based on customer location"""
        settings = SalesSettings.get_settings()
        
        if not settings.enable_tax_calculation:
            return 0
        
        from .models import TaxRate
        # Try to find tax rate for customer's country
        if self.billing_country:
            tax_rate = TaxRate.objects.filter(
                applies_to_countries=self.billing_country,
                is_active=True
            ).first()
            if tax_rate:
                return tax_rate.rate
        
        return settings.default_tax_rate    

    @property
    def display_name(self):
        """Get appropriate display name based on customer type"""
        if self.customer_type == self.CustomerType.BUSINESS and self.company_name:
            return self.company_name
        return self.full_name or f"{self.first_name} {self.last_name}"

    @property
    def billing_full_address(self):
        """Return formatted billing address"""
        parts = [self.billing_address_line1]
        if self.billing_address_line2:
            parts.append(self.billing_address_line2)
        if self.billing_city:
            parts.append(self.billing_city.name)
        if self.billing_region:
            parts.append(self.billing_region.name)
        if self.billing_country:
            parts.append(self.billing_country.name)
        if self.billing_postal_code:
            parts.append(self.billing_postal_code)
        return ", ".join(parts)

    @property
    def shipping_full_address(self):
        """Return formatted shipping address"""
        if self.same_as_billing:
            return self.billing_full_address
        parts = [self.shipping_address_line1]
        if self.shipping_address_line2:
            parts.append(self.shipping_address_line2)
        if self.shipping_city:
            parts.append(self.shipping_city.name)
        if self.shipping_region:
            parts.append(self.shipping_region.name)
        if self.shipping_country:
            parts.append(self.shipping_country.name)
        if self.shipping_postal_code:
            parts.append(self.shipping_postal_code)
        return ", ".join(parts)

    @property
    def total_due(self):
        """Calculate total amount due from all invoices"""
        from sales.models import SalesInvoice
        invoices = SalesInvoice.objects.filter(customer=self, status='unpaid')
        total = invoices.aggregate(
            total_due=Sum(F('total_amount') - F('amount_paid'))
        )['total_due']
        return total or 0

    @property
    def total_orders(self):
        """Total number of orders placed by this customer"""
        return self.sales_orders.count()

    @property
    def lifetime_value(self):
        """Total value of all orders placed"""
        total = self.sales_orders.aggregate(
            total=Sum(F('lines__quantity') * F('lines__price'))
        )['total']
        return total or 0

    def update_order_statistics(self):
        """Update order statistics after new order"""
        orders = self.sales_orders.filter(status='completed')
        self.total_orders_count = orders.count()
        total_value = orders.aggregate(
            total=Sum(F('lines__quantity') * F('lines__price'))
        )['total'] or 0
        if self.total_orders_count > 0:
            self.average_order_value = total_value / self.total_orders_count
        self.save(update_fields=['total_orders_count', 'average_order_value'])

class Quotation(models.Model):
    """Pre-sales quotation that can be converted to order"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent to Customer'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('converted', 'Converted to Order'),
    ]
    
    quotation_number = models.CharField(max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.PROTECT, 
        related_name='quotations'
    )
    quotation_date = models.DateField(auto_now_add=True)
    valid_until = models.DateField()
    
    # Financial
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    
    # Tracking
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_quotations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Reference to converted order
    converted_order = models.ForeignKey(
        'SalesOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='source_quotation'
    )
    
    class Meta:
        ordering = ['-quotation_date', '-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['quotation_number']),
            models.Index(fields=['customer', 'quotation_date']),
        ]
    
    def __str__(self):
        return self.quotation_number or f"Q-{self.id}"
    
    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        if not settings.enable_quotations:
            raise ValidationError("Quotations are not enabled")
        
        if not self.quotation_number:
            last_quote = Quotation.objects.filter(
                quotation_number__startswith=settings.quotation_prefix
            ).order_by('-id').first()
            
            if last_quote and last_quote.quotation_number:
                try:
                    last_num = int(last_quote.quotation_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.quotation_number = f"{settings.quotation_prefix}{last_num + 1:04d}"
        
        if not self.valid_until:
            self.valid_until = timezone.now().date() + timedelta(days=settings.quotation_valid_days)
        
        super().save(*args, **kwargs)
    
    def convert_to_order(self):
        """Convert quotation to sales order"""
        settings = SalesSettings.get_settings()
        
        if not settings.enable_sales_orders:
            raise ValidationError("Sales orders are not enabled")
        
        if self.status != 'accepted':
            raise ValidationError("Only accepted quotations can be converted to orders.")
        
        # Create order
        from .models import SalesOrder
        order = SalesOrder.objects.create(
            customer=self.customer,
            warehouse=None,  # You'll need to handle this
            status='draft',
            notes=f"Converted from Quotation {self.quotation_number}"
        )
        
        # Copy lines
        for quote_line in self.quotation_lines.all():
            order.lines.create(
                product=quote_line.product,
                quantity=quote_line.quantity,
                price=quote_line.price,
                discount_percent=quote_line.discount_percent
            )
        
        self.status = 'converted'
        self.converted_order = order
        self.save()
        
        return order
    
    def expire_if_past_date(self):
        """Auto-expire quotations past valid date"""
        if self.status in ['draft', 'sent'] and self.valid_until < timezone.now().date():
            self.status = 'expired'
            self.save(update_fields=['status'])


class QuotationLine(models.Model):
    """Lines for quotation"""
    quotation = models.ForeignKey(
        Quotation, 
        on_delete=models.CASCADE, 
        related_name='quotation_lines'
    )
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        # Apply discount only if enabled
        discount = self.discount_percent if settings.enable_discounts else 0
        self.line_total = self.quantity * self.price * (1 - discount/100)
        super().save(*args, **kwargs)   

# sales/models.py - Enhanced SalesOrder class

class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('confirmed', 'Confirmed'),
        ('partial', 'Partially Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('invoiced', 'Invoiced'),
    ]

    order_number = models.CharField(max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE,
        related_name='sales_orders'
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', 
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    order_date = models.DateField(auto_now_add=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Financial
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Tax
    tax_rate = models.ForeignKey(
        'TaxRate',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    tax_exempt = models.BooleanField(default=False)
    tax_exemption_reason = models.CharField(max_length=255, blank=True)
    
    # Approval fields
    requires_approval = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        blank=True,
        null=True
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_orders'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_orders'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sales_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['order_date']),
            models.Index(fields=['customer', 'order_date']),
            models.Index(fields=['approval_status']),
        ]

    def __str__(self):
        return self.order_number or f"SO-{self.id}"

    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        if not settings.enable_sales_orders:
            raise ValidationError("Sales orders are not enabled")
        
        if not self.order_number:
            last_order = SalesOrder.objects.filter(
                order_number__startswith=settings.order_prefix
            ).order_by('-id').first()
            
            if last_order and last_order.order_number:
                try:
                    last_num = int(last_order.order_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.order_number = f"{settings.order_prefix}{last_num + 1:04d}"
        
        super().save(*args, **kwargs)

    def request_approval(self, user):
        """Request approval for order"""
        settings = SalesSettings.get_settings()
        
        if not settings.enable_order_approval:
            self.status = 'confirmed'
            self.save(update_fields=['status'])
            return self.confirm()
        
        self.requires_approval = True
        self.approval_status = 'pending'
        self.requested_by = user
        self.status = 'pending_approval'
        self.save(update_fields=['requires_approval', 'approval_status', 'requested_by', 'status'])

    def approve(self, user):
        """Approve the order"""
        settings = SalesSettings.get_settings()
        
        self.approval_status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
        
        if settings.auto_confirm_approved_orders:
            self.confirm()

    def reject(self, user, reason):
        """Reject the order"""
        self.approval_status = 'rejected'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.approval_notes = reason
        self.status = 'cancelled'
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'approval_notes', 'status'])

    def check_approval_required(self):
        """Check if order requires approval based on settings"""
        settings = SalesSettings.get_settings()
        
        if not settings.enable_order_approval:
            return False
        
        return self.total_amount >= settings.require_approval_for_amount

    def confirm(self):
        """Confirm the order"""
        if self.status not in ['draft', 'pending_approval']:
            raise ValidationError("Only draft or pending approval orders can be confirmed.")

        settings = SalesSettings.get_settings()

        # Check credit limit if enabled
        if settings.enable_credit_limit:
            credit_ok, message = self.customer.check_credit_limit(self.total_amount)
            if not credit_ok:
                raise ValidationError(message)

        # Check stock availability (unless backorders enabled)
        if not settings.enable_backorders:
            availability = self.check_stock_availability()
            unavailable = [a for a in availability if not a['available']]
            if unavailable:
                msg = "Insufficient stock for:\n"
                for u in unavailable:
                    msg += f"  - {u['line'].product.name}: Required {u['required']}, Available {u['stock']}\n"
                raise ValidationError(msg)

        self.status = 'confirmed'
        self.save(update_fields=['status'])
        
        # Update customer's last order date
        Customer.objects.filter(pk=self.customer.pk).update(
            last_order_date=timezone.now()
        )

    def check_stock_availability(self):
        """Check if sufficient stock is available"""
        availability = []
        for line in self.lines.all():
            warehouse = line.warehouse or self.warehouse
            total_stock = Stock.objects.filter(
                product=line.product,
                warehouse=warehouse
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            available = total_stock >= line.quantity
            availability.append({
                'line': line,
                'available': available,
                'stock': total_stock,
                'required': line.quantity,
                'warehouse': warehouse
            })
        return availability

    @transaction.atomic
    def deliver_line(self, line_id, quantity_to_deliver):
        """Deliver a partial quantity for a specific line"""
        line = self.lines.get(id=line_id)
        
        if quantity_to_deliver <= 0:
            raise ValidationError("Quantity to deliver must be positive.")
        
        if line.delivered_quantity + quantity_to_deliver > line.quantity:
            raise ValidationError(
                f"Cannot deliver more than ordered quantity. "
                f"Ordered: {line.quantity}, Already delivered: {line.delivered_quantity}"
            )

        warehouse = line.warehouse or self.warehouse
        
        # Get stock and reduce
        stocks = Stock.objects.filter(
            product=line.product,
            warehouse=warehouse
        ).order_by('id')
        
        remaining = quantity_to_deliver
        for stock in stocks:
            if remaining <= 0:
                break
                
            deduct = min(stock.quantity, remaining)
            if deduct > 0:
                stock.quantity -= deduct
                stock.save()
                remaining -= deduct
        
        if remaining > 0:
            raise ValidationError(f"Insufficient stock. Could only deliver {quantity_to_deliver - remaining} units.")

        line.delivered_quantity += quantity_to_deliver
        line.save()

        # Update order status
        if all(line.delivered_quantity == line.quantity for line in self.lines.all()):
            self.status = 'completed'
        elif any(line.delivered_quantity > 0 for line in self.lines.all()):
            self.status = 'partial'
        self.save()

    @property
    def total_amount(self):
        total = self.lines.aggregate(
            total=Sum(F('quantity') * F('price') * (1 - F('discount_percent')/100))
        )['total'] or 0
        
        settings = SalesSettings.get_settings()
        
        # Add tax if enabled
        if settings.enable_tax_calculation and not self.tax_exempt:
            tax_rate = self.tax_rate.rate if self.tax_rate else self.customer.get_applicable_tax_rate()
            self.tax_amount = total * (tax_rate / 100)
        else:
            self.tax_amount = 0
        
        return total + self.tax_amount

    @property
    def total_delivered(self):
        return self.lines.aggregate(
            total=Sum('delivered_quantity')
        )['total'] or 0

    @property
    def is_fully_delivered(self):
        return all(
            line.delivered_quantity == line.quantity 
            for line in self.lines.all()
        )

# sales/models.py - Enhanced SalesOrderLine class

class SalesOrderLine(models.Model):
    order = models.ForeignKey(
        SalesOrder, 
        on_delete=models.CASCADE, 
        related_name="lines"
    )
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Warehouse & Delivery
    warehouse = models.ForeignKey(
        'inventory.Warehouse', 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True
    )
    section = models.ForeignKey(
        'inventory.WarehouseSection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    delivered_quantity = models.PositiveIntegerField(default=0)
    
    # Profit tracking (optional)
    cost_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    profit_margin = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    profit_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    class Meta:
        unique_together = ('order', 'product')
        indexes = [
            models.Index(fields=['order', 'product']),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        # Calculate profit if enabled
        if settings.enable_profit_tracking:
            if not self.cost_price and self.product:
                self.cost_price = self.product.cost_price
            
            if self.cost_price:
                self.profit_amount = (self.price - self.cost_price) * self.quantity
                if self.price > 0:
                    self.profit_margin = ((self.price - self.cost_price) / self.price) * 100
        
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        discount = self.discount_percent if SalesSettings.get_settings().enable_discounts else 0
        return self.quantity * self.price * (1 - discount/100)

    @property
    def remaining_quantity(self):
        return self.quantity - self.delivered_quantity

    @property
    def is_fully_delivered(self):
        return self.delivered_quantity >= self.quantity



# sales/models.py - Add Quotation classes


# sales/models.py - Add Delivery Note classes

class DeliveryNote(models.Model):
    """Delivery note for shipped orders"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    delivery_number = models.CharField(max_length=50, unique=True, blank=True)
    sales_order = models.ForeignKey(
        SalesOrder, 
        on_delete=models.PROTECT, 
        related_name='delivery_notes'
    )
    delivery_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Shipping info
    shipping_address = models.TextField()
    tracking_number = models.CharField(max_length=100, blank=True)
    courier_name = models.CharField(max_length=100, blank=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_delivery_notes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-delivery_date', '-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['delivery_number']),
        ]
    
    def __str__(self):
        return self.delivery_number or f"DN-{self.id}"
    
    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        if not settings.enable_delivery_notes:
            raise ValidationError("Delivery notes are not enabled")
        
        if not self.delivery_number:
            last_dn = DeliveryNote.objects.filter(
                delivery_number__startswith=settings.delivery_note_prefix
            ).order_by('-id').first()
            
            if last_dn and last_dn.delivery_number:
                try:
                    last_num = int(last_dn.delivery_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.delivery_number = f"{settings.delivery_note_prefix}{last_num + 1:04d}"
        
        if not self.shipping_address and self.sales_order:
            self.shipping_address = self.sales_order.customer.shipping_full_address
        
        super().save(*args, **kwargs)
    
    def mark_shipped(self, tracking_number, courier):
        """Mark delivery note as shipped"""
        self.status = 'shipped'
        self.tracking_number = tracking_number
        self.courier_name = courier
        self.save(update_fields=['status', 'tracking_number', 'courier_name'])
    
    def mark_delivered(self):
        """Mark delivery note as delivered"""
        self.status = 'delivered'
        self.save(update_fields=['status'])


class DeliveryNoteLine(models.Model):
    """Lines in delivery note"""
    delivery_note = models.ForeignKey(
        DeliveryNote, 
        on_delete=models.CASCADE, 
        related_name='lines'
    )
    order_line = models.ForeignKey(
        SalesOrderLine, 
        on_delete=models.PROTECT,
        related_name='delivery_lines'
    )
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    
    # For tracking partial deliveries
    previous_delivered = models.PositiveIntegerField(default=0)
    remaining = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ('delivery_note', 'order_line')
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        if not self.remaining:
            self.remaining = self.order_line.remaining_quantity
        super().save(*args, **kwargs)   

# sales/models.py - Add Sales Return classes

class SalesReturn(models.Model):
    """Customer returns / RMA"""
    
    RETURN_TYPE_CHOICES = [
        ('damaged', 'Damaged Goods'),
        ('defective', 'Defective Product'),
        ('wrong_item', 'Wrong Item Sent'),
        ('customer_decision', 'Customer Changed Mind'),
        ('warranty', 'Warranty Claim'),
    ]
    
    STATUS_CHOICES = [
        ('requested', 'Return Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('received', 'Goods Received'),
        ('inspected', 'Inspected'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
    ]
    
    return_number = models.CharField(max_length=50, unique=True, blank=True)
    sales_order = models.ForeignKey(
        SalesOrder, 
        on_delete=models.PROTECT, 
        related_name='returns'
    )
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.PROTECT,
        related_name='returns'
    )
    return_date = models.DateField(auto_now_add=True)
    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    
    reason = models.TextField()
    
    RESOLUTION_CHOICES = [
        ('refund', 'Refund'),
        ('replace', 'Replace'),
        ('credit', 'Credit Note'),
        ('repair', 'Repair'),
    ]
    resolution = models.CharField(
        max_length=20,
        choices=RESOLUTION_CHOICES,
        default='refund'
    )
    
    # Financial
    refund_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    restocking_fee = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    # Tracking
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='approved_returns'
    )
    received_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='received_returns'
    )
    inspected_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='inspected_returns'
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-return_date', '-id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['return_number']),
            models.Index(fields=['customer', 'return_date']),
        ]
    
    def __str__(self):
        return self.return_number or f"RMA-{self.id}"
    
    def save(self, *args, **kwargs):
        settings = SalesSettings.get_settings()
        
        if not settings.enable_sales_returns:
            raise ValidationError("Sales returns are not enabled")
        
        if not self.return_number:
            last_return = SalesReturn.objects.filter(
                return_number__startswith=settings.return_prefix
            ).order_by('-id').first()
            
            if last_return and last_return.return_number:
                try:
                    last_num = int(last_return.return_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.return_number = f"{settings.return_prefix}{last_num + 1:04d}"
        
        if not self.customer and self.sales_order:
            self.customer = self.sales_order.customer
        
        super().save(*args, **kwargs)
    
    def approve(self, user):
        """Approve return"""
        self.status = 'approved'
        self.approved_by = user
        self.save(update_fields=['status', 'approved_by'])
    
    def reject(self, user, reason):
        """Reject return"""
        self.status = 'rejected'
        self.approved_by = user
        self.notes = f"{self.notes}\nRejection reason: {reason}"
        self.save(update_fields=['status', 'approved_by', 'notes'])
    
    def receive_goods(self, user):
        """Record that goods have been received"""
        self.status = 'received'
        self.received_by = user
        self.save(update_fields=['status', 'received_by'])
    
    def complete_inspection(self, user, notes=""):
        """Complete inspection of returned goods"""
        self.status = 'inspected'
        self.inspected_by = user
        if notes:
            self.notes = f"{self.notes}\nInspection notes: {notes}"
        self.save(update_fields=['status', 'inspected_by', 'notes'])
    
    def process_refund(self, amount=None):
        """Process refund for return"""
        if amount:
            self.refund_amount = amount
        
        # Create credit note or refund record
        from .models import CreditNote
        credit_note = CreditNote.objects.create(
            customer=self.customer,
            sales_return=self,
            amount=self.refund_amount or self.total_refund_amount,
            reason=f"Refund for return {self.return_number}"
        )
        
        self.status = 'refunded'
        self.save(update_fields=['status'])
        
        return credit_note
    
    @property
    def total_refund_amount(self):
        """Calculate total refund amount from lines"""
        total = self.lines.aggregate(
            total=Sum(F('quantity') * F('refund_price'))
        )['total'] or 0
        return total - self.restocking_fee


class SalesReturnLine(models.Model):
    """Lines in return"""
    sales_return = models.ForeignKey(
        SalesReturn, 
        on_delete=models.CASCADE, 
        related_name='lines'
    )
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    refund_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    CONDITION_CHOICES = [
        ('new', 'Like New'),
        ('used', 'Used'),
        ('damaged', 'Damaged'),
        ('defective', 'Defective'),
    ]
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    
    inspected = models.BooleanField(default=False)
    inspection_notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

# sales/models.py - Add Tax Rate class


# sales/models.py - Add Credit Note class

class CreditNote(models.Model):
    """Credit notes for refunds and adjustments"""
    
    credit_number = models.CharField(max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.PROTECT,
        related_name='credit_notes'
    )
    sales_return = models.ForeignKey(
        SalesReturn, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_notes'
    )
    invoice = models.ForeignKey(
        'SalesInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_notes'
    )
    
    credit_date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    remaining_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Amount still available for use"
    )
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_credit_notes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-credit_date', '-id']
    
    def __str__(self):
        return self.credit_number or f"CN-{self.id}"
    
    def save(self, *args, **kwargs):
        if not self.credit_number:
            last_cn = CreditNote.objects.filter(
                credit_number__startswith='CN-'
            ).order_by('-id').first()
            
            if last_cn and last_cn.credit_number:
                try:
                    last_num = int(last_cn.credit_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            
            self.credit_number = f"CN-{last_num + 1:04d}"
        
        if not self.remaining_amount:
            self.remaining_amount = self.amount
        
        super().save(*args, **kwargs)
    
    def apply_to_invoice(self, invoice, amount):
        """Apply credit note to an invoice"""
        if amount > self.remaining_amount:
            raise ValidationError(f"Insufficient credit. Available: {self.remaining_amount}")
        
        # Create credit application record
        CreditApplication.objects.create(
            credit_note=self,
            invoice=invoice,
            amount=amount
        )
        
        self.remaining_amount -= amount
        if self.remaining_amount <= 0:
            self.status = 'applied'
        self.save()
        
        # Update invoice
        invoice.amount_paid += amount
        if invoice.amount_paid >= invoice.total_amount:
            invoice.status = 'paid'
        elif invoice.amount_paid > 0:
            invoice.status = 'partial'
        invoice.save()


class CreditApplication(models.Model):
    """Record of credit note applications to invoices"""
    credit_note = models.ForeignKey(
        CreditNote, 
        on_delete=models.CASCADE,
        related_name='applications'
    )
    invoice = models.ForeignKey(
        'SalesInvoice',
        on_delete=models.CASCADE,
        related_name='credit_applications'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    applied_at = models.DateTimeField(auto_now_add=True)
    applied_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    
    class Meta:
        ordering = ['-applied_at']                      
class SalesInvoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True
    )
    order = models.OneToOneField(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='sales_invoice'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='sales_invoices'
    )
    invoice_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['customer', 'invoice_date']),
        ]

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last_invoice = SalesInvoice.objects.filter(
                invoice_number__startswith='INV-'
            ).order_by('-id').first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_num = int(last_invoice.invoice_number.split('-')[-1])
                except (IndexError, ValueError):
                    last_num = 0
            else:
                last_num = 0
            self.invoice_number = f"INV-{last_num + 1:04d}"
        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.balance_due > 0 and self.due_date < timezone.now().date()

    def register_payment(self, amount, payment_method, reference=""):
        """Register a payment against this invoice"""
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")
        
        if self.balance_due < amount:
            raise ValidationError(f"Payment exceeds balance due. Balance: {self.balance_due}")
        
        self.amount_paid += amount
        
        # Update status
        if self.amount_paid >= self.total_amount:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partial'
        
        self.save()
        
        # Create payment record
        Payment.objects.create(
            invoice=self,
            amount=amount,
            payment_method=payment_method,
            reference=reference
        )


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Credit/Debit Card'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('online', 'Online Payment'),
    ]

    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    payment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount} ({self.payment_method})"