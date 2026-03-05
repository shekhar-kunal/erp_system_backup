from config_settings.models import PricingConfig, Currency
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone
from mptt.models import MPTTModel, TreeForeignKey
from django.core.cache import cache
from django.db import transaction

# -----------------------------
# Mixins for Reusability
# -----------------------------
class TimestampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class ActiveMixin(models.Model):
    active = models.BooleanField(default=True)
    
    class Meta:
        abstract = True

# ============================================
# NOTE: SEOMixin is commented out as these fields will move to e-commerce app
# ============================================
# class SEOMixin(models.Model):
#     meta_title = models.CharField(max_length=255, blank=True)
#     meta_description = models.TextField(blank=True)
#     tags = models.CharField(max_length=255, blank=True)
#     
#     class Meta:
#         abstract = True


# -----------------------------
# Unit Model - WITH HARDCODED UNIT TYPES
# -----------------------------
class Unit(models.Model):
    # Hardcoded unit type choices - CANNOT be changed by users
    UNIT_TYPE_CHOICES = [
        ('weight', 'Weight (Mass)'),
        ('volume', 'Volume (Capacity)'),
        ('length', 'Length (Distance)'),
        ('area', 'Area (Surface Size)'),
        ('standard', 'Standard (Discrete)'),
        ('packaging', 'Primary Packaging'),
        ('time', 'Duration / Time'),
        ('digital', 'Digital Storage'),
        ('energy', 'Energy'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=20)
    code = models.CharField(max_length=20, unique=True)
    
    # Use hardcoded choices instead of ForeignKey
    unit_type = models.CharField(
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default='standard',
        help_text="Type of unit (Weight, Volume, Length, etc.)"
    )
    
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['unit_type', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['unit_type', 'is_active']),
        ]
        
    def __str__(self):
        return f"{self.name} ({self.short_name})"
    
    def clean(self):
        # Strip whitespace from name/short_name/code before any checks.
        if self.name:
            self.name = self.name.strip()
        if self.short_name:
            self.short_name = self.short_name.strip()

        # Normalize code to uppercase first so uniqueness validation
        # sees the final stored value, not the raw input.
        if self.code:
            self.code = self.code.strip().upper()
        elif self.short_name:
            self.code = self.short_name.upper()

        # Check code uniqueness with a user-friendly error.
        if self.code:
            qs = Unit.objects.filter(code=self.code)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'code': f"A unit with code '{self.code}' already exists."})

        # Check name uniqueness case-insensitively — "BOX" and "box" are the same unit.
        if self.name:
            qs = Unit.objects.filter(name__iexact=self.name)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                existing = qs.first().name
                raise ValidationError({'name': f"A unit with the name '{existing}' already exists (names are case-insensitive)."})

    def save(self, *args, **kwargs):
        # Auto-generate code from short_name if not provided
        if not self.code and self.short_name:
            self.code = self.short_name.upper()
        if self.code:
            self.code = self.code.upper()
        super().save(*args, **kwargs)
    
    def used_in_products(self):
        return self.base_products.count() + self.packing_units.count()


# -----------------------------
# Brand Model
# -----------------------------
class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    logo = models.ImageField(upload_to='brands/', blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True)
    
    # ============================================
    # TODO: E-COMMERCE FIELDS - Uncomment when moving to e-commerce app
    # ============================================
    # meta_title = models.CharField(max_length=255, blank=True)
    # meta_description = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active', 'is_featured']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    def product_count(self):
        return self.products.count()
    product_count.short_description = "Products"


# -----------------------------
# ModelNumber Model
# -----------------------------
class ModelNumber(models.Model):
    """Separate model for better management and reusability"""
    name = models.CharField(max_length=100, help_text="e.g., iPhone 15 Pro")
    code = models.CharField(max_length=50, unique=True, help_text="e.g., A3102")
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='models')
    description = models.TextField(blank=True)
    
    # Technical specifications (optional JSON field for flexibility)
    specifications = models.JSONField(default=dict, blank=True, help_text="Technical specs in JSON format")
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['brand', 'name']
        unique_together = ('brand', 'code')
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['brand', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.brand.name} {self.name} ({self.code})"


# -----------------------------
# Product Category (MPTT Ready)
# -----------------------------
class ProductCategory(MPTTModel, TimestampMixin):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    
    # Status & Ordering
    active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    
    # ============================================
    # TODO: E-COMMERCE FIELDS - Uncomment when moving to e-commerce app
    # These SEO fields are customer-facing and belong in e-commerce
    # ============================================
    # meta_title = models.CharField(max_length=255, blank=True)
    # meta_description = models.TextField(blank=True)
    # tags = models.CharField(max_length=255, blank=True)
    
    # Business Rules
    code = models.CharField(max_length=50, blank=True, unique=True, null=True)
    default_discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # UI Helpers
    color = models.CharField(max_length=7, blank=True, help_text="Hex color code (e.g., #FF0000)")
    icon = models.ImageField(upload_to='category_icons/', blank=True, null=True)
    
    # Internal Notes
    notes = models.TextField(blank=True)

    class MPTTMeta:
        order_insertion_by = ['position', 'name']

    class Meta:
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['code']),
            models.Index(fields=['active', 'is_featured']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        cache.delete('category_tree')

    def __str__(self):
        return self.name

    def full_path(self):
        if self.parent:
            return f"{self.parent.full_path()} > {self.name}"
        return self.name

    def product_count(self):
        return self.products.count()
    product_count.short_description = "Products"
    
    def get_all_children_count(self):
        """Get total products including subcategories"""
        total = self.products.count()
        for child in self.get_children():
            total += child.get_all_children_count()
        return total
    
    get_total_products = get_all_children_count
    get_total_products.short_description = "Total Products (incl. subcategories)"


# -----------------------------
# Product Image Model
# -----------------------------
class ProductImage(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='products/gallery/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    

    class Meta:
        ordering = ['position']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_primary=True),
                name='unique_primary_image_per_product'
            )
        ]



    def __str__(self):
        # Create descriptive string with position and primary status
        primary_str = " (PRIMARY)" if self.is_primary else ""
        position_str = f" [pos:{self.position}]" if self.position else ""
        
        # Truncate filename if too long
        filename = self.image.name.split('/')[-1] if self.image else "No image"
        if len(filename) > 30:
            filename = filename[:27] + "..."
        
        return f"{self.product.name} - {filename}{primary_str}{position_str}"
    
    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_primary:
                ProductImage.objects.filter(product=self.product).exclude(pk=self.pk).update(is_primary=False)
            super().save(*args, **kwargs)


# -----------------------------
# Product Attribute Models
# -----------------------------
class ProductAttribute(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class ProductAttributeValue(models.Model):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=255)
    code = models.SlugField()
    
    class Meta:
        unique_together = ('attribute', 'code')
        ordering = ['attribute', 'value']
    
    def __str__(self):
        return f"{self.attribute.name}: {self.value}"

class ProductAttributeAssignment(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='attribute_assignments')
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE)
    value = models.ForeignKey(ProductAttributeValue, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('product', 'attribute')
    
    def __str__(self):
        return f"{self.product.name} - {self.attribute.name}: {self.value.value}"


# -----------------------------
# Product Variant Model
# -----------------------------
class ProductVariant(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    price_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.IntegerField(default=0)
    attributes = models.JSONField(default=dict, help_text="Store variant attributes like size, color")
    image = models.ImageField(upload_to='product_variants/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('product', 'sku')
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['product', 'is_active']),
        ]
    
    def __str__(self):
        # Create a more descriptive string
        attr_display = ""
        if self.attributes and isinstance(self.attributes, dict):
            attr_parts = [f"{k}: {v}" for k, v in self.attributes.items()]
            if attr_parts:
                attr_display = f" ({', '.join(attr_parts)})"
        
        return f"{self.product.name} - {self.name}{attr_display}"
    
    @property
    def effective_price(self):
        return self.product.price + self.price_adjustment


# -----------------------------
# Product Price History
# -----------------------------
class ProductPriceHistory(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='price_history')
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['product', '-changed_at']),
        ]
    
    def __str__(self):
        # Format: "Product Name: $100.00 → $120.00 (2024-01-15)"
        date_str = self.changed_at.strftime('%Y-%m-%d') if self.changed_at else 'Unknown date'
        user_str = f" by {self.changed_by.username}" if self.changed_by else ""
        reason_str = f" - {self.reason}" if self.reason else ""
        
        return f"{self.product.name}: ${self.old_price} → ${self.new_price}{reason_str} ({date_str}{user_str})"


# ============================================
# PRICE LIST MANAGEMENT - For Multi-Tier Pricing
# ============================================

class PriceList(models.Model):
    """Define different price tiers (Retail, Wholesale, Distributor, etc.)"""
    
    name = models.CharField(max_length=100, help_text="e.g., Retail Price, Wholesale Price")
    code = models.CharField(max_length=20, unique=True, help_text="e.g., RETAIL, WHOLESALE")
    description = models.TextField(blank=True)
    
    # Priority/Order (lower number = higher priority)
    priority = models.IntegerField(default=0, help_text="Lower number = higher priority")
    
    # Discount method
    DISCOUNT_METHOD_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('percentage', 'Percentage off base'),
        ('formula', 'Formula based'),
    ]
    
    discount_method = models.CharField(
        max_length=20,
        choices=DISCOUNT_METHOD_CHOICES,
        default='fixed'
    )
    
    # Default discount percentage (if method is percentage)
    default_discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Default discount % for this price list"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Default price list for new products")
    
    # Which customer types can use this price list
    applicable_to_retail = models.BooleanField(default=True)
    applicable_to_wholesale = models.BooleanField(default=False)
    applicable_to_distributor = models.BooleanField(default=False)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['priority', 'name']
        verbose_name = "Price List"
        verbose_name_plural = "Price Lists"
    
    def __str__(self):
        # Add status indicators
        status = []
        if self.is_default:
            status.append("DEFAULT")
        if not self.is_active:
            status.append("INACTIVE")
        
        status_str = f" [{'|'.join(status)}]" if status else ""
        
        return f"{self.name} ({self.code}){status_str}"
    
    def save(self, *args, **kwargs):
        """
        FIX B: Wrap in atomic transaction so clearing other defaults and saving
        this record succeed or fail together.
        Use exclude(pk=self.pk) to avoid clearing ourselves before we save.
        """
        #from django.db import transaction

        with transaction.atomic():
            if self.is_default:
                PriceList.objects.exclude(pk=self.pk).filter(
                    is_default=True
                ).update(is_default=False)
            super().save(*args, **kwargs)
    
    def product_count(self):
        """Return number of products using this price list"""
        return self.product_prices.count()
    product_count.short_description = "Products"


class ProductPrice(models.Model):
    """Product prices for different price lists with multi-currency support"""
    
    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='price_list_prices'
    )
    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name='product_prices'
    )
    
    # ============================================
    # MULTI-CURRENCY SUPPORT
    # ============================================
    currency = models.ForeignKey(
        'config_settings.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Currency for this price (defaults to product currency)"
    )
    
    # The actual price for this product in this price list
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Price for this product in this price list"
    )
    
    # Optional: Override discount percentage (if price list uses percentage)
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Override the default discount % for this product"
    )
    
    # Optional: Minimum quantity for this price to apply
    min_quantity = models.PositiveIntegerField(
        default=1,
        help_text="Minimum quantity to get this price"
    )
    
    # Optional: Date range for promotional pricing
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    
    # Exchange rate at time of price creation (for historical accuracy)
    exchange_rate_at_creation = models.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Exchange rate when this price was set"
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('product', 'price_list', 'min_quantity')
        ordering = ['product', 'price_list__priority', 'min_quantity']
        indexes = [
            models.Index(fields=['product', 'price_list']),
            models.Index(fields=['price_list', 'min_quantity']),
            models.Index(fields=['currency']),  # Added currency index
            models.Index(fields=['product', 'currency']),  # Compound index
        ]
    
    def __str__(self):
        # Create descriptive string with quantity, validity and currency
        qty_str = f" (min {self.min_quantity})" if self.min_quantity > 1 else ""
        
        # Add validity indicator
        validity = ""
        if self.valid_from or self.valid_to:
            now = timezone.now()
            if self.valid_from and self.valid_from > now:
                validity = " [future]"
            elif self.valid_to and self.valid_to < now:
                validity = " [expired]"
            else:
                validity = " [active]"
        
        # Format price with currency
        if self.currency:
            price_str = self.currency.format_amount(self.price)
        else:
            price_str = f"${self.price}"
        
        return f"{self.product.name} - {self.price_list.name}: {price_str}{qty_str}{validity}"
    
    def save(self, *args, **kwargs):
        """Save with currency defaults and exchange rate capture"""
        # If no currency set, use product's currency
        if not self.currency and self.product.currency:
            self.currency = self.product.currency
        
        # Capture exchange rate at creation if not set
        if not self.exchange_rate_at_creation and self.currency:
            self.exchange_rate_at_creation = self.currency.exchange_rate
        
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Check if this price is currently valid based on dates"""
        from django.utils import timezone
        now = timezone.now()
        if self.valid_from and self.valid_from > now:
            return False
        if self.valid_to and self.valid_to < now:
            return False
        return True
    
    # ============================================
    # CURRENCY METHODS
    # ============================================
    
    @property
    def effective_currency(self):
        """Get the effective currency (price currency or product currency)"""
        return self.currency or (self.product.currency if self.product else None)
    
    @property
    def formatted_price(self):
        """Get price formatted with currency"""
        currency = self.effective_currency
        if currency:
            return currency.format_amount(self.price)
        return f"${self.price}"
    
    def get_price_in_currency(self, target_currency):
        """
        Convert this price to another currency
        
        Args:
            target_currency: Currency object or currency code
        
        Returns:
            Decimal: Price in target currency
        """
        from config_settings.utils.currency import CurrencyConverter
        
        source_currency = self.effective_currency
        if not source_currency or not target_currency or source_currency == target_currency:
            return self.price
        
        converter = CurrencyConverter()
        return converter.convert(self.price, source_currency, target_currency)
    
    def get_price_with_markup(self, markup_percentage):
        """
        Apply markup percentage to price
        
        Args:
            markup_percentage: Markup percentage (e.g., 20 for 20%)
        
        Returns:
            Decimal: Price with markup applied
        """
        return self.price * (1 + markup_percentage/100)
    
    def get_price_with_discount(self, discount_percentage):
        """
        Apply discount percentage to price
        
        Args:
            discount_percentage: Discount percentage (e.g., 15 for 15%)
        
        Returns:
            Decimal: Price with discount applied
        """
        return self.price * (1 - discount_percentage/100)
    
    def compare_to_product_base(self):
        """
        Compare this price to product's base price
        
        Returns:
            Dict with comparison data
        """
        base_price = self.product.base_price or self.product.price
        difference = self.price - base_price
        percentage = (difference / base_price * 100) if base_price else 0
        
        return {
            'base_price': base_price,
            'this_price': self.price,
            'difference': difference,
            'percentage': percentage,
            'is_higher': difference > 0,
            'is_lower': difference < 0,
            'is_equal': difference == 0
        }
    
    def get_historical_value(self, target_date):
        """
        Get the approximate value of this price at a past date
        (using exchange rate at that time if available)
        
        Args:
            target_date: Date to calculate value for
        
        Returns:
            Decimal: Estimated price value at target date
        """
        from config_settings.models import ExchangeRateHistory
        
        if not self.currency:
            return self.price
        
        # Try to find exchange rate for that date
        try:
            rate_history = ExchangeRateHistory.objects.filter(
                currency=self.currency,
                date__lte=target_date
            ).order_by('-date').first()
            
            if rate_history:
                # Price in base currency at creation
                base_value = self.price / self.exchange_rate_at_creation
                # Convert to target date value
                return base_value * rate_history.exchange_rate
        except Exception:
            pass

        return self.price
    
    @classmethod
    def get_prices_for_customer(cls, product, customer, quantity=1):
        """
        Get all applicable prices for a customer with currency conversion
        """
        from django.db.models import Q
        from django.utils import timezone
        
        now = timezone.now()
        
        # Build base queryset
        queryset = cls.objects.filter(
            product=product,
            min_quantity__lte=quantity
        )
        
        # Apply date filters
        queryset = queryset.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now)
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=now)
        )
        
        # Optimize with select_related
        prices = queryset.select_related('price_list', 'currency')
        
        # Get customer's currency if available
        customer_currency = None
        if customer and hasattr(customer, 'currency'):
            customer_currency = customer.currency
        
        # Build result list
        result = []
        for price in prices:
            base_data = {
                'price_list': price.price_list,
                'original_price': price.price,
                'original_currency': price.effective_currency,
                'min_quantity': price.min_quantity,
                'valid': price.is_valid(),
                'id': price.id,
            }
            
            # Handle currency conversion
            if customer_currency and price.effective_currency and price.effective_currency != customer_currency:
                from config_settings.utils.currency import CurrencyConverter
                converter = CurrencyConverter()
                converted_price = converter.convert(
                    price.price, 
                    price.effective_currency, 
                    customer_currency
                )
                base_data.update({
                    'price': converted_price,
                    'currency': customer_currency,
                    'formatted': customer_currency.format_amount(converted_price),
                    'converted': True
                })
            else:
                base_data.update({
                    'price': price.price,
                    'currency': price.effective_currency,
                    'formatted': price.formatted_price,
                    'converted': False
                })
            
            result.append(base_data)
        
        return result


# -----------------------------
# Product Model (UPDATED with Price Lists)
# -----------------------------
class Product(TimestampMixin, ActiveMixin, models.Model):
    class ProductType(models.TextChoices):
        STOCKABLE = 'ST', _('Stockable')
        CONSUMABLE = 'CO', _('Consumable')
        SERVICE = 'SE', _('Service')

    class Visibility(models.TextChoices):
        PUBLIC = 'public', _('Public')
        PRIVATE = 'private', _('Private')

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='products'
    )
    related_products = models.ManyToManyField('self', blank=True)
    
    # Brand and Model
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name='products',
        null=True,
        blank=True,
        help_text="Product brand/manufacturer"
    )
    
    model_number = models.ForeignKey(
        ModelNumber,
        on_delete=models.PROTECT,
        related_name='products',
        null=True,
        blank=True,
        help_text="Specific model number"
    )
    
    model_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display model name (can be auto-filled from model_number)"
    )
    
    # Base Unit
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='base_products',
        help_text="Base unit for inventory tracking (e.g., PCS, KG)",
        limit_choices_to={'is_active': True},
        null=True,
        blank=True
    )
    
    # ============================================
    # CORE PRODUCT FIELDS
    # ============================================
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)  # Purchase cost
    
    # ============================================
    # MULTI-CURRENCY SUPPORT
    # ============================================
    currency = models.ForeignKey(
        'config_settings.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Currency for base price"
    )
    
    # Type & Status
    product_type = models.CharField(
        max_length=2,
        choices=ProductType.choices,
        default=ProductType.STOCKABLE
    )
    is_featured = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    visibility = models.CharField(
        max_length=20, 
        choices=Visibility.choices, 
        default=Visibility.PUBLIC
    )

    # Media
    main_image = models.ImageField(upload_to='products/', blank=True, null=True)

    # Description
    description = models.TextField(blank=True, null=True)

    # Identification
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)

    # Shipping & Packaging
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    dimensions = models.CharField(max_length=50, blank=True, help_text="e.g., 10x5x2 cm")
    multi_pack = models.IntegerField(default=1, help_text="e.g., 6-pack")

    # ============================================
    # PRICE LIST RELATIONSHIP
    # ============================================
    
    # Base price (used as reference)
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Base price for calculations"
    )
    
    # Default price list for this product
    default_price_list = models.ForeignKey(
        PriceList,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_for_products',
        help_text="Default price list for this product"
    )

    # Internal Notes
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['barcode']),
            models.Index(fields=['active', 'is_featured']),
            models.Index(fields=['created_at']),
            models.Index(fields=['category', 'active']),
            models.Index(fields=['product_type']),
            models.Index(fields=['brand', 'active']),
            models.Index(fields=['model_number']),
            models.Index(fields=['base_unit']),
            models.Index(fields=['price']),
            models.Index(fields=['-created_at', 'active']),
            models.Index(fields=['currency']),  # Added currency index
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name='price_positive'),
            models.CheckConstraint(condition=models.Q(cost__gte=0), name='cost_positive'),
        ]

    def __str__(self):
        category_name = self.category.name if self.category else "No Category"
        brand_name = self.brand.name if self.brand else "No Brand"
        price_str = self.formatted_price
        return f"{self.name} ({brand_name} - {category_name}) - {price_str}"

    def clean(self):
        """Model validation"""
        if self.discount_price and self.discount_price >= self.price:
            raise ValidationError({
                'discount_price': 'Discount price must be less than regular price'
            })

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        
        # Auto-generate SKU if not provided
        if not self.sku and self.name:
            self.sku = self._generate_sku()
        
    #    # Track price changes
    #    old_price = None
    #    old_currency = None
    #    if self.pk:
    #        try:
    #            old_instance = Product.objects.get(pk=self.pk)
    #            old_price = old_instance.price
    #            old_currency = old_instance.currency
    #        except Product.DoesNotExist:
    #            pass
        
        super().save(*args, **kwargs)
        
    #    # Track price changes after save
    #    if old_price is not None and old_price != self.price:
    #        reason = "Price updated"
    #        if old_currency != self.currency:
    #            reason += f" and currency changed from {old_currency} to {self.currency}"
    #        
    #        ProductPriceHistory.objects.create(
    #            product=self,
    #            old_price=old_price,
    #            new_price=self.price,
    #            reason=reason
    #        )
        
        # Clear cache
        transaction.on_commit(lambda: cache.delete(f'product_{self.id}'))
        transaction.on_commit(lambda: cache.delete('featured_products'))

    def _generate_sku(self):
        """Generate a unique SKU for the product"""
        if not self.name:
            return None
        
        base = slugify(self.name)[:8].upper()
        sku = base
        counter = 1
        
        while Product.objects.filter(sku=sku).exists():
            sku = f"{base[:5]}{counter:03d}"
            counter += 1
        
        return sku

    # ============================================
    # CURRENCY METHODS
    # ============================================
    
    @property
    def formatted_price(self):
        """Get price formatted with currency"""
        if self.currency:
            return self.currency.format_amount(self.price)
        return f"${self.price}"
    
    @property
    def formatted_discount_price(self):
        """Get discount price formatted with currency"""
        if not self.discount_price:
            return None
        if self.currency:
            return self.currency.format_amount(self.discount_price)
        return f"${self.discount_price}"
    
    @property
    def formatted_cost(self):
        """Get cost formatted with currency"""
        if self.currency:
            return self.currency.format_amount(self.cost)
        return f"${self.cost}"
    
    def get_price_in_currency(self, target_currency, quantity=1):
        """
        Get product price in specified currency
        
        Args:
            target_currency: Currency object or currency code
            quantity: Quantity for bulk pricing
        
        Returns:
            Decimal: Price in target currency
        """
        from config_settings.utils.currency import CurrencyConverter
        
        # Get base price (considering quantity and price lists)
        base_price = self.get_price_for_customer(None, quantity)
        
        if not target_currency or target_currency == self.currency:
            return base_price
        
        converter = CurrencyConverter()
        return converter.convert(base_price, self.currency, target_currency)
    
    def get_price_for_customer_in_currency(self, customer, target_currency=None, quantity=1):
        """
        Get price for customer in specified currency
        
        Args:
            customer: Customer object
            target_currency: Target currency (defaults to customer's currency)
            quantity: Quantity for bulk pricing
        
        Returns:
            Decimal: Price in target currency
        """
        # Get price in base currency
        price_in_base = self.get_price_for_customer(customer, quantity)
        
        # Determine target currency
        if not target_currency and customer and hasattr(customer, 'currency'):
            target_currency = customer.currency
        elif not target_currency:
            target_currency = self.currency
        
        if not target_currency or target_currency == self.currency:
            return price_in_base
        
        # Convert to target currency
        from config_settings.utils.currency import CurrencyConverter
        converter = CurrencyConverter()
        return converter.convert(price_in_base, self.currency, target_currency)
    
    def get_all_prices_in_currency(self, target_currency=None):
        """
        Get all price list prices converted to target currency
        
        Args:
            target_currency: Target currency (defaults to product currency)
        
        Returns:
            List of dictionaries with converted prices
        """
        target = target_currency or self.currency
        prices = []
        
        for product_price in self.price_list_prices.select_related('price_list', 'currency').all():
            price_amount = product_price.price
            price_currency = product_price.currency or self.currency
            
            if target and price_currency != target:
                from config_settings.utils.currency import CurrencyConverter
                converter = CurrencyConverter()
                converted_price = converter.convert(price_amount, price_currency, target)
            else:
                converted_price = price_amount
                target = price_currency
            
            prices.append({
                'price_list': product_price.price_list.name,
                'original_price': price_amount,
                'original_currency': price_currency.code if price_currency else None,
                'price': converted_price,
                'currency': target.code if target else None,
                'formatted_price': target.format_amount(converted_price) if target else f"${converted_price}",
                'min_quantity': product_price.min_quantity,
                'is_valid': product_price.is_valid()
            })
        
        return prices

    # ============================================
    # MEDIA METHODS
    # ============================================
    
    def get_primary_image(self):
        """Get primary image or main_image"""
        primary = self.gallery_images.filter(is_primary=True).first()
        if primary:
            return primary.image
        return self.main_image

    # ============================================
    # PACKING METHODS
    # ============================================
    
    def get_all_packings(self):
        """Get all available packings"""
        return self.packings.select_related('packing_unit').all()

    def get_default_packing(self):
        """Get default packing"""
        return self.packings.filter(is_default=True).first()
    
    def get_packing_price_in_currency(self, packing, target_currency=None):
        """Get packing price in specified currency"""
        if not packing.price:
            return None
        
        if not target_currency or target_currency == self.currency:
            return packing.price
        
        from config_settings.utils.currency import CurrencyConverter
        converter = CurrencyConverter()
        return converter.convert(packing.price, self.currency, target_currency)

    # ============================================
    # PRICE LIST METHODS
    # ============================================
    
    def _get_price_list_for_customer(self, customer):
        """Determine which price list applies to a customer"""
        if not customer:
            return None
        
        # Get customer's pricing tier
        tier = getattr(customer, 'pricing_tier', 'retail') if hasattr(customer, 'pricing_tier') else 'retail'
        
        # Find applicable price list
        if tier == 'retail':
            return PriceList.objects.filter(
                applicable_to_retail=True,
                is_active=True
            ).order_by('priority').first()
        elif tier == 'wholesale':
            return PriceList.objects.filter(
                applicable_to_wholesale=True,
                is_active=True
            ).order_by('priority').first()
        elif tier == 'distributor':
            return PriceList.objects.filter(
                applicable_to_distributor=True,
                is_active=True
            ).order_by('priority').first()
        
        return None

    def get_price_for_customer(self, customer, quantity=1):
        """
        Get the appropriate price for a specific customer in base currency
        
        Args:
            customer: Customer object with pricing_tier attribute
            quantity: Quantity being purchased (for min_quantity rules)
        
        Returns:
            Decimal: The appropriate price for this customer
        """
        #from config_settings.models import PricingConfig
        
        config = PricingConfig.get_config()
        
        # If single price model, return base price
        if config.pricing_model == 'single':
            return self.base_price or self.price
        
        # Determine which price list applies to this customer
        price_list = self._get_price_list_for_customer(customer)
        
        # If no price list found, use base price
        if not price_list:
            return self.base_price or self.price
        
        # Try to find a matching price in this price list
        try:
            product_price = self.price_list_prices.filter(
                price_list=price_list,
                min_quantity__lte=quantity
            ).order_by('-min_quantity').first()
            
            if product_price and product_price.is_valid():
                return product_price.price
                
        except Exception:
            pass
        
        return self.base_price or self.price
    
    def get_all_prices(self):
        """Get all prices for this product across all price lists"""
        prices = []
        for product_price in self.price_list_prices.select_related('price_list', 'currency').all():
            currency = product_price.currency or self.currency
            prices.append({
                'price_list': product_price.price_list.name,
                'price': product_price.price,
                'currency': currency.code if currency else None,
                'formatted_price': currency.format_amount(product_price.price) if currency else f"${product_price.price}",
                'min_quantity': product_price.min_quantity,
                'is_valid': product_price.is_valid()
            })
        return prices
    
    def update_prices_from_base(self, price_list, percentage=None):
        """
        Update prices for a price list based on base price
        If percentage provided, calculate price = base_price * (1 - percentage/100)
        """
        if percentage is not None:
            new_price = self.base_price * (1 - percentage/100)
            ProductPrice.objects.update_or_create(
                product=self,
                price_list=price_list,
                defaults={
                    'price': new_price,
                    'currency': self.currency
                }
            )


# -----------------------------
# Product Packing
# -----------------------------
class ProductPacking(models.Model):
    product = models.ForeignKey(
        'Product',  # Changed from importing Product
        on_delete=models.CASCADE,
        related_name='packings'
    )

    packing_unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name='packing_units',
        limit_choices_to={'is_active': True}
    )

    quantity = models.PositiveIntegerField(
        help_text="How many base units inside this packing (e.g. 20 PCS)"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Optional special price for this packing"
    )

    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ('product', 'packing_unit', 'quantity')
        indexes = [
            models.Index(fields=['product', 'is_default']),
        ]

    def __str__(self):
        base_unit = self.product.base_unit.short_name if self.product.base_unit else "unit"
        return f"{self.product.name} - 1 {self.packing_unit.short_name} = {self.quantity} {base_unit}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                ProductPacking.objects.filter(product=self.product).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)