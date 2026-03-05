from django import forms
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re
from config_settings.models import Currency
from rbac.models import Role

class WelcomeForm(forms.Form):
    """Step 1: Language and basic settings"""
    language = forms.ChoiceField(
        choices=[
            ('en', 'English'),
            ('de', 'German (Deutsch)'),
            ('ru', 'Russian (Русский)'),
            ('uk', 'Ukrainian (Українська)'),
        ],
        initial='en',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_language'})
    )
    country = forms.ChoiceField(
        choices=[
            ('US', 'United States'),
            ('GB', 'United Kingdom'),
            ('DE', 'Germany (Deutschland)'),
            ('UA', 'Ukraine (Україна)'),
            ('IN', 'India'),
            ('CN', 'China (中国)'),
        ],
        initial='US',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_country'})
    )
    timezone = forms.ChoiceField(
        choices=[
            # Americas
            ('America/New_York',    'UTC-5   New York (Eastern)'),
            ('America/Chicago',     'UTC-6   Chicago (Central)'),
            ('America/Denver',      'UTC-7   Denver (Mountain)'),
            ('America/Los_Angeles', 'UTC-8   Los Angeles (Pacific)'),
            # Europe
            ('Europe/London',       'UTC+0   London (GMT)'),
            ('Europe/Berlin',       'UTC+1   Berlin / Frankfurt (CET)'),
            ('Europe/Kyiv',         'UTC+2   Kyiv (EET)'),
            ('Europe/Moscow',       'UTC+3   Moscow (MSK)'),
            # Asia
            ('Asia/Dubai',          'UTC+4   Dubai (GST)'),
            ('Asia/Kolkata',        'UTC+5:30  Mumbai / New Delhi (IST)'),
            ('Asia/Shanghai',       'UTC+8   Beijing / Shanghai (CST)'),
            ('Asia/Tokyo',          'UTC+9   Tokyo (JST)'),
        ],
        initial='America/New_York',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_timezone'})
    )
    currency = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        empty_label=None,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_currency'})
    )
    date_format = forms.ChoiceField(
        choices=[
            ('Y-m-d', 'YYYY-MM-DD  e.g. 2025-03-04  (ISO / China)'),
            ('d/m/Y', 'DD/MM/YYYY  e.g. 04/03/2025  (UK / India)'),
            ('m/d/Y', 'MM/DD/YYYY  e.g. 03/04/2025  (USA)'),
            ('d.m.Y', 'DD.MM.YYYY  e.g. 04.03.2025  (Germany / Ukraine)'),
            ('d-m-Y', 'DD-MM-YYYY  e.g. 04-03-2025  (EU dash)'),
        ],
        initial='Y-m-d',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_date_format'})
    )


class CompanyForm(forms.Form):
    """Step 2: Company information"""
    company_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., ABC Corporation'})
    )
    legal_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Legal name if different'})
    )
    tax_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VAT / Tax ID'})
    )
    registration_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company registration #'})
    )
    
    # Address
    address_line1 = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address'})
    )
    address_line2 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apt, Suite, etc.'})
    )
    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'})
    )
    state = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State / Province'})
    )
    postal_code = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal code'})
    )
    country = forms.ChoiceField(
        choices=[
            ('US', 'United States'), ('GB', 'United Kingdom'), 
            ('CA', 'Canada'), ('AU', 'Australia'), ('IN', 'India')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Contact
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 234 567 8900'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'company@example.com'})
    )
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.example.com'})
    )


class AdminUserForm(forms.Form):
    """Step 3: Create admin user"""
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'John'})
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Doe'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@example.com'})
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'admin'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'})
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 234 567 8900'})
    )
    
    def clean_username(self):
        username = self.cleaned_data['username']
        from accounts.models import CustomUser
        if CustomUser.objects.filter(username=username).exists():
            raise ValidationError("Username already exists")
        return username
    
    def clean_email(self):
        email = self.cleaned_data['email']
        from accounts.models import CustomUser
        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError("Email already exists")
        return email
    
    def clean_password(self):
        password = self.cleaned_data['password']
        # Password strength validation
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        if not re.search(r'[A-Z]', password):
            raise ValidationError("Password must contain at least one uppercase letter")
        if not re.search(r'[0-9]', password):
            raise ValidationError("Password must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError("Password must contain at least one special character")
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        
        if password and confirm and password != confirm:
            raise ValidationError("Passwords do not match")
        
        return cleaned_data


class ModulesForm(forms.Form):
    """Step 4: Select modules to install"""
    MODULE_CHOICES = [
        ('sales', 'Sales Management'),
        ('purchasing', 'Purchasing'),
        ('inventory', 'Inventory Management'),
        ('accounting', 'Accounting'),
        ('products', 'Products & Pricing'),
        ('reports', 'Reporting & Analytics'),
        ('hr', 'Human Resources'),
        ('crm', 'Customer Relationship Management'),
    ]
    
    modules = forms.MultipleChoiceField(
        choices=MODULE_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'module-checkbox'}),
        initial=['sales', 'purchasing', 'inventory', 'accounting', 'products', 'reports']
    )
    
    install_sample_data = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class ConfigurationForm(forms.Form):
    """Step 5: System configuration"""
    # Financial settings
    fiscal_year_start = forms.ChoiceField(
        choices=[(str(i), f'{i}') for i in range(1, 13)],
        initial='1',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    fiscal_year_start_day = forms.ChoiceField(
        choices=[(str(i), f'{i}') for i in range(1, 32)],
        initial='1',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tax_system = forms.ChoiceField(
        choices=[
            ('none', 'No Tax'),
            ('sales_tax', 'Sales Tax'),
            ('vat', 'Value Added Tax (VAT)'),
            ('gst', 'Goods & Services Tax (GST)'),
        ],
        initial='sales_tax',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    default_tax_rate = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=10.0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    # Inventory settings
    enable_batches = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    enable_serials = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    allow_negative_stock = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # Email settings
    smtp_server = forms.CharField(
        initial='smtp.gmail.com',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    smtp_port = forms.IntegerField(
        initial=587,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    smtp_username = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'your-email@gmail.com'})
    )
    smtp_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'})
    )
    smtp_use_tls = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class ReviewForm(forms.Form):
    """Step 6: Review and confirm"""
    confirm = forms.BooleanField(
        required=True,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )