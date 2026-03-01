from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class Country(models.Model):
    """
    Master data for countries
    """
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=3, unique=True, help_text="ISO 3166-1 alpha-3 code")
    iso_code = models.CharField(max_length=2, unique=True, help_text="ISO 3166-1 alpha-2 code")
    phone_code = models.CharField(max_length=10, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    currency_symbol = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.IntegerField(default=0, help_text="Display order")
    
    # Common timezone for the country
    default_timezone = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'name']
        verbose_name_plural = "Countries"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['iso_code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        # Prevent deactivating if used by vendors/customers
        if not self.is_active and self.pk:
            # Check if used by any vendor
            vendor_count = self.vendors.count() if hasattr(self, 'vendors') else 0
            # Check if used by any customer (billing or shipping)
            billing_count = self.billing_customers.count() if hasattr(self, 'billing_customers') else 0
            shipping_count = self.shipping_customers.count() if hasattr(self, 'shipping_customers') else 0
            
            total_used = vendor_count + billing_count + shipping_count
            
            if total_used > 0:
                raise ValidationError({
                    'is_active': _(
                        f'Cannot deactivate this country because it is used by '
                        f'{vendor_count} vendors and {billing_count + shipping_count} customers.'
                    )
                })

    def save(self, *args, **kwargs):
        if not self.code and self.iso_code:
            self.code = self.iso_code.upper()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_cities(self):
        """Get total number of cities in this country"""
        return self.cities.count()

    @property
    def total_regions(self):
        """Get total number of regions in this country"""
        return self.regions.count()

    @property
    def usage_count(self):
        """Get total usage count across all modules"""
        vendor_count = self.vendors.count() if hasattr(self, 'vendors') else 0
        billing_count = self.billing_customers.count() if hasattr(self, 'billing_customers') else 0
        shipping_count = self.shipping_customers.count() if hasattr(self, 'shipping_customers') else 0
        return vendor_count + billing_count + shipping_count


class Region(models.Model):
    """
    Regions/States/Provinces within countries
    """
    name = models.CharField(max_length=100)
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name='regions'
    )
    code = models.CharField(max_length=10, blank=True, help_text="State/Region code")
    is_active = models.BooleanField(default=True)
    position = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['country', 'position', 'name']
        unique_together = ('name', 'country')
        verbose_name_plural = "Regions"
        indexes = [
            models.Index(fields=['country', 'name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name}, {self.country.name}"

    def clean(self):
        # Prevent deactivating if used by cities
        if not self.is_active and self.pk:
            city_count = self.cities.count() if hasattr(self, 'cities') else 0
            if city_count > 0:
                raise ValidationError({
                    'is_active': _(
                        f'Cannot deactivate this region because it is used by {city_count} cities.'
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_cities(self):
        """Get total number of cities in this region"""
        return self.cities.count() if hasattr(self, 'cities') else 0


class City(models.Model):
    """
    Master data for cities (linked to countries and regions)
    """
    name = models.CharField(max_length=100)
    country = models.ForeignKey(
        Country, 
        on_delete=models.CASCADE,
        related_name='cities'
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cities',
        help_text="State/Region this city belongs to"
    )
    state = models.CharField(max_length=100, blank=True, help_text="State or province (legacy field)")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_capital = models.BooleanField(default=False)
    population = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True, help_text="Postal code prefix")
    position = models.IntegerField(default=0, help_text="Display order")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['country', 'region', 'position', 'name']
        unique_together = ('name', 'country', 'region')
        verbose_name_plural = "Cities"
        indexes = [
            models.Index(fields=['country', 'name']),
            models.Index(fields=['region']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_capital']),
        ]

    def __str__(self):
        if self.region:
            return f"{self.name}, {self.region.name}, {self.country.name}"
        elif self.state:
            return f"{self.name}, {self.state}, {self.country.name}"
        return f"{self.name}, {self.country.name}"

    def clean(self):
        # Prevent deactivating if used by vendors/customers
        if not self.is_active and self.pk:
            # Check if used by any vendor
            vendor_count = self.vendors.count() if hasattr(self, 'vendors') else 0
            # Check if used by any customer (billing or shipping)
            billing_count = self.billing_customers.count() if hasattr(self, 'billing_customers') else 0
            shipping_count = self.shipping_customers.count() if hasattr(self, 'shipping_customers') else 0
            
            total_used = vendor_count + billing_count + shipping_count
            
            if total_used > 0:
                raise ValidationError({
                    'is_active': _(
                        f'Cannot deactivate this city because it is used by '
                        f'{vendor_count} vendors and {billing_count + shipping_count} customers.'
                    )
                })

    def save(self, *args, **kwargs):
        # Auto-set state from region if available
        if self.region and not self.state:
            self.state = self.region.name
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Get full city name with region and country"""
        parts = [self.name]
        if self.region:
            parts.append(self.region.name)
        elif self.state:
            parts.append(self.state)
        parts.append(self.country.name)
        return ", ".join(parts)

    @property
    def usage_count(self):
        """Get total usage count across all modules"""
        vendor_count = self.vendors.count() if hasattr(self, 'vendors') else 0
        billing_count = self.billing_customers.count() if hasattr(self, 'billing_customers') else 0
        shipping_count = self.shipping_customers.count() if hasattr(self, 'shipping_customers') else 0
        return vendor_count + billing_count + shipping_count
    
class AddressMixin(models.Model):
    """
    Abstract base model for consistent address structure across all models
    """
    address_line1 = models.CharField(max_length=255, verbose_name="Address Line 1")
    address_line2 = models.CharField(max_length=255, blank=True, verbose_name="Address Line 2")
    country = models.ForeignKey(
        'core.Country',
        on_delete=models.PROTECT,
        related_name='%(class)s_country',
        verbose_name="Country"
    )
    region = models.ForeignKey(
        'core.Region',
        on_delete=models.PROTECT,
        related_name='%(class)s_region',
        verbose_name="Region/State",
        null=True,
        blank=True
    )
    city = models.ForeignKey(
        'core.City',
        on_delete=models.PROTECT,
        related_name='%(class)s_city',
        verbose_name="City"
    )
    postal_code = models.CharField(max_length=20, verbose_name="Postal/ZIP Code")
    
    class Meta:
        abstract = True
    
    @property
    def full_address(self):
        """Return formatted full address"""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        if self.city:
            parts.append(self.city.name)
        if self.region:
            parts.append(self.region.name)
        if self.country:
            parts.append(self.country.name)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)
    
    @property
    def short_address(self):
        """Return short address (city, country)"""
        parts = []
        if self.city:
            parts.append(self.city.name)
        if self.country:
            parts.append(self.country.name)
        return ", ".join(parts)    
    
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
