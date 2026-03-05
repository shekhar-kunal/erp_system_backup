from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum, F, Q
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta, date
from decimal import Decimal
import calendar
from sales.models import SalesOrder, Customer
from purchasing.models import PurchaseOrder, Vendor


# ==================== EXISTING MODELS (PRESERVED) ====================

class Invoice(models.Model):
    """
    Sales Invoice - generated from Sales Orders
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('void', 'Void'),
    ]

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated if left blank"
    )
    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='accounting_invoice',
        help_text="The sales order this invoice is generated from"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='accounting_invoices',
        null=True,
        blank=True
    )
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_date = models.DateTimeField(null=True, blank=True)
    paid_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-invoice_date', '-id']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['customer', 'invoice_date']),
        ]

    def __str__(self):
        return self.invoice_number or f"INV-{self.id}"

    def save(self, *args, **kwargs):
        # Auto-generate invoice number
        if not self.invoice_number:
            with transaction.atomic():
                last_invoice = Invoice.objects.select_for_update().filter(
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

        # Auto-set customer from sales order
        if self.sales_order and not self.customer:
            self.customer = self.sales_order.customer

        # Auto-calculate amounts
        if self.sales_order:
            self.total_amount = self.sales_order.total_amount
            self.net_amount = self.total_amount + self.tax_amount - self.discount_amount

        # Auto-set due date if not provided (default 30 days)
        if not self.due_date:
            self.due_date = self.invoice_date + timedelta(days=30)

        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """Calculate remaining balance"""
        return self.net_amount - self.amount_paid

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        return (self.status not in ['paid', 'cancelled', 'void'] and 
                self.due_date < timezone.now().date() and 
                self.balance_due > 0)

    def register_payment(self, amount, payment_method, reference="", payment_date=None):
        """
        Register a payment against this invoice
        """
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")

        if self.balance_due < amount:
            raise ValidationError(
                f"Payment exceeds balance due. Balance: {self.balance_due}"
            )

        with transaction.atomic():
            create_kwargs = {
                'payment_type': 'customer',
                'invoice': self,
                'amount': amount,
                'payment_method': payment_method,
                'reference': reference,
                'status': 'completed',
            }
            if payment_date:
                create_kwargs['payment_date'] = payment_date
            payment = Payment.objects.create(**create_kwargs)

            self.amount_paid += amount

            if self.amount_paid >= self.net_amount:
                self.status = 'paid'
                self.paid_date = timezone.now()
            elif self.amount_paid > 0:
                self.status = 'partial'

            self.save(update_fields=['amount_paid', 'status', 'paid_date'])

        return payment

    def mark_as_sent(self):
        """Mark invoice as sent to customer"""
        self.status = 'sent'
        self.sent_date = timezone.now()
        self.save(update_fields=['status', 'sent_date'])

    def cancel(self):
        """Cancel the invoice"""
        if self.amount_paid > 0:
            raise ValidationError("Cannot cancel invoice with payments. Void it instead.")
        self.status = 'cancelled'
        self.save(update_fields=['status'])

    def void(self):
        """Void the invoice (when payments exist)"""
        self.status = 'void'
        self.save(update_fields=['status'])

    def post_to_accounting(self):
        """Create and post a journal entry for this invoice."""
        settings = AccountingSettings.get_settings()
        ar_account = settings.default_ar_account
        sales_account = settings.default_sales_account
        if not ar_account or not sales_account:
            return None

        tax_account = settings.default_tax_account if self.tax_amount else None
        discount_account = settings.default_discount_account if self.discount_amount else None
        # Use detailed split only when all needed accounts are configured
        use_detail = (
            (not self.tax_amount or tax_account) and
            (not self.discount_amount or discount_account)
        )

        with transaction.atomic():
            entry = JournalEntry.objects.create(
                journal_type='sale',
                entry_date=self.invoice_date,
                description=f"Invoice {self.invoice_number}",
                invoice=self,
            )
            JournalLine.objects.create(
                journal_entry=entry, account=ar_account,
                debit_credit='debit', amount=self.net_amount,
            )
            if use_detail:
                # CR Revenue: gross; CR Tax: tax; DR Discount: discount
                JournalLine.objects.create(
                    journal_entry=entry, account=sales_account,
                    debit_credit='credit', amount=self.total_amount,
                )
                if self.tax_amount and tax_account:
                    JournalLine.objects.create(
                        journal_entry=entry, account=tax_account,
                        debit_credit='credit', amount=self.tax_amount,
                    )
                if self.discount_amount and discount_account:
                    JournalLine.objects.create(
                        journal_entry=entry, account=discount_account,
                        debit_credit='debit', amount=self.discount_amount,
                    )
            else:
                # Simplified: net against revenue
                JournalLine.objects.create(
                    journal_entry=entry, account=sales_account,
                    debit_credit='credit', amount=self.net_amount,
                )
            entry.post()
        return entry


class Bill(models.Model):
    """
    Purchase Bill - generated from Purchase Orders
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    bill_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated if left blank"
    )
    purchase_order = models.OneToOneField(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name='bill',
        help_text="The purchase order this bill is generated from"
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name='bills',
        null=True,
        blank=True
    )
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-bill_date', '-id']
        indexes = [
            models.Index(fields=['bill_number']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['vendor', 'bill_date']),
        ]

    def __str__(self):
        return self.bill_number or f"BILL-{self.id}"

    def save(self, *args, **kwargs):
        # Auto-generate bill number
        if not self.bill_number:
            with transaction.atomic():
                last_bill = Bill.objects.select_for_update().filter(
                    bill_number__startswith='BILL-'
                ).order_by('-id').first()
                if last_bill and last_bill.bill_number:
                    try:
                        last_num = int(last_bill.bill_number.split('-')[-1])
                    except (IndexError, ValueError):
                        last_num = 0
                else:
                    last_num = 0
                self.bill_number = f"BILL-{last_num + 1:04d}"

        # Auto-set vendor from purchase order
        if self.purchase_order and not self.vendor:
            self.vendor = self.purchase_order.vendor

        # Auto-calculate amounts
        if self.purchase_order:
            self.total_amount = self.purchase_order.total_amount
            self.net_amount = self.total_amount + self.tax_amount - self.discount_amount

        # Auto-set due date if not provided (default 30 days)
        if not self.due_date:
            self.due_date = self.bill_date + timedelta(days=30)

        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """Calculate remaining balance to pay"""
        return self.net_amount - self.amount_paid

    @property
    def is_overdue(self):
        """Check if bill is overdue"""
        return (self.status not in ['paid', 'cancelled'] and 
                self.due_date < timezone.now().date() and 
                self.balance_due > 0)

    def register_payment(self, amount, payment_method, reference="", payment_date=None):
        """
        Register a payment against this bill
        """
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")

        if self.balance_due < amount:
            raise ValidationError(
                f"Payment exceeds balance due. Balance: {self.balance_due}"
            )

        with transaction.atomic():
            create_kwargs = {
                'payment_type': 'vendor',
                'bill': self,
                'amount': amount,
                'payment_method': payment_method,
                'reference': reference,
                'status': 'completed',
            }
            if payment_date:
                create_kwargs['payment_date'] = payment_date
            payment = Payment.objects.create(**create_kwargs)

            self.amount_paid += amount

            if self.amount_paid >= self.net_amount:
                self.status = 'paid'
                self.paid_date = timezone.now()
            elif self.amount_paid > 0:
                self.status = 'partial'

            self.save(update_fields=['amount_paid', 'status', 'paid_date'])

        return payment

    def cancel(self):
        """Cancel the bill"""
        if self.amount_paid > 0:
            raise ValidationError("Cannot cancel bill with payments.")
        self.status = 'cancelled'
        self.save(update_fields=['status'])

    def post_to_accounting(self):
        """Create and post a journal entry for this bill."""
        settings = AccountingSettings.get_settings()
        ap_account = settings.default_ap_account
        purchase_account = settings.default_purchase_account
        if not ap_account or not purchase_account:
            return None

        tax_account = settings.default_tax_account if self.tax_amount else None
        discount_account = settings.default_discount_account if self.discount_amount else None
        use_detail = (
            (not self.tax_amount or tax_account) and
            (not self.discount_amount or discount_account)
        )

        with transaction.atomic():
            entry = JournalEntry.objects.create(
                journal_type='purchase',
                entry_date=self.bill_date,
                description=f"Bill {self.bill_number}",
                bill=self,
            )
            JournalLine.objects.create(
                journal_entry=entry, account=ap_account,
                debit_credit='credit', amount=self.net_amount,
            )
            if use_detail:
                # DR Purchases: gross; DR Tax: tax; CR Discount: discount
                JournalLine.objects.create(
                    journal_entry=entry, account=purchase_account,
                    debit_credit='debit', amount=self.total_amount,
                )
                if self.tax_amount and tax_account:
                    JournalLine.objects.create(
                        journal_entry=entry, account=tax_account,
                        debit_credit='debit', amount=self.tax_amount,
                    )
                if self.discount_amount and discount_account:
                    JournalLine.objects.create(
                        journal_entry=entry, account=discount_account,
                        debit_credit='credit', amount=self.discount_amount,
                    )
            else:
                JournalLine.objects.create(
                    journal_entry=entry, account=purchase_account,
                    debit_credit='debit', amount=self.net_amount,
                )
            entry.post()
        return entry


class Payment(models.Model):
    """
    Payment tracking for both customer and vendor payments
    """
    PAYMENT_TYPE_CHOICES = [
        ('customer', 'Customer Payment (Received)'),
        ('vendor', 'Vendor Payment (Sent)'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('cheque', 'Cheque'),
        ('online', 'Online Payment'),
        ('other', 'Other'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    payment_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated if left blank"
    )
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Related objects (one of these should be set)
    invoice = models.ForeignKey(
        Invoice,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='payments'
    )
    bill = models.ForeignKey(
        Bill,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='payments'
    )
    
    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    reference = models.CharField(max_length=100, blank=True, help_text="Reference number (cheque no, transaction ID, etc.)")
    notes = models.TextField(blank=True)
    
    # Dates
    payment_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date', '-id']
        indexes = [
            models.Index(fields=['payment_type']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return self.payment_number or f"PAY-{self.id}"

    def save(self, *args, **kwargs):
        # Auto-generate payment number
        if not self.payment_number:
            with transaction.atomic():
                last_payment = Payment.objects.select_for_update().filter(
                    payment_number__startswith='PAY-'
                ).order_by('-id').first()
                if last_payment and last_payment.payment_number:
                    try:
                        last_num = int(last_payment.payment_number.split('-')[-1])
                    except (IndexError, ValueError):
                        last_num = 0
                else:
                    last_num = 0
                self.payment_number = f"PAY-{last_num + 1:04d}"

        # Validate that either invoice or bill is set, but not both
        if self.payment_type == 'customer' and not self.invoice:
            raise ValidationError("Customer payment must be linked to an invoice.")
        if self.payment_type == 'vendor' and not self.bill:
            raise ValidationError("Vendor payment must be linked to a bill.")
        if self.invoice and self.bill:
            raise ValidationError("Payment cannot be linked to both invoice and bill.")
        
        super().save(*args, **kwargs)

    def process(self):
        """Process the payment (update invoice/bill)"""
        if self.status != 'pending':
            raise ValidationError("Only pending payments can be processed.")

        if self.payment_type == 'customer' and self.invoice:
            self.invoice.register_payment(
                amount=self.amount,
                payment_method=self.payment_method,
                reference=self.reference
            )
        elif self.payment_type == 'vendor' and self.bill:
            self.bill.register_payment(
                amount=self.amount,
                payment_method=self.payment_method,
                reference=self.reference
            )

        self.status = 'completed'
        self.save()

    def post_to_accounting(self):
        """Create and post a journal entry for this payment."""
        settings = AccountingSettings.get_settings()
        cash_account = settings.default_cash_account
        if not cash_account:
            return None

        with transaction.atomic():
            if self.payment_type == 'customer':
                ar_account = settings.default_ar_account
                if not ar_account:
                    return None
                entry = JournalEntry.objects.create(
                    journal_type='cash_receipt',
                    entry_date=self.payment_date,
                    description=f"Payment {self.payment_number}",
                    payment=self,
                )
                JournalLine.objects.create(
                    journal_entry=entry, account=cash_account,
                    debit_credit='debit', amount=self.amount,
                )
                JournalLine.objects.create(
                    journal_entry=entry, account=ar_account,
                    debit_credit='credit', amount=self.amount,
                )
            else:
                ap_account = settings.default_ap_account
                if not ap_account:
                    return None
                entry = JournalEntry.objects.create(
                    journal_type='cash_payment',
                    entry_date=self.payment_date,
                    description=f"Payment {self.payment_number}",
                    payment=self,
                )
                JournalLine.objects.create(
                    journal_entry=entry, account=ap_account,
                    debit_credit='debit', amount=self.amount,
                )
                JournalLine.objects.create(
                    journal_entry=entry, account=cash_account,
                    debit_credit='credit', amount=self.amount,
                )
            entry.post()
        return entry


# ==================== NEW MODELS (ENHANCEMENTS) ====================

class FiscalYear(models.Model):
    """
    Fiscal year configuration for accounting periods
    """
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_fiscal_years'
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-start_date']
        unique_together = ['start_date', 'end_date']
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"
    
    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")
        
        # Check for overlapping fiscal years
        overlapping = FiscalYear.objects.filter(
            Q(start_date__lte=self.end_date, end_date__gte=self.start_date)
        ).exclude(pk=self.pk)
        
        if overlapping.exists():
            raise ValidationError("Fiscal year overlaps with existing fiscal year")
    
    def close(self, user):
        """Close fiscal year - prevents new entries"""
        if self.is_closed:
            raise ValidationError("Fiscal year already closed")
        
        # Check if all periods are closed
        if self.periods.filter(is_closed=False).exists():
            raise ValidationError("All periods must be closed before closing fiscal year")
        
        self.is_closed = True
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save()


class FiscalPeriod(models.Model):
    """
    Accounting periods within a fiscal year
    """
    PERIOD_TYPES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('custom', 'Custom'),
    ]
    
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='periods')
    period_number = models.PositiveIntegerField(help_text="1-12 for monthly, 1-4 for quarterly")
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['fiscal_year', 'period_number']
        unique_together = ['fiscal_year', 'period_number']
    
    def __str__(self):
        return f"Period {self.period_number}: {self.start_date} - {self.end_date}"
    
    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")
    
    def close(self, user):
        """Close period - prevents new entries"""
        if self.is_closed:
            raise ValidationError("Period already closed")
        
        self.is_closed = True
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save()


class Account(models.Model):
    """
    Chart of Accounts - Core of double-entry accounting
    """
    ACCOUNT_TYPES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    NORMAL_BALANCE = {
        'asset': 'debit',
        'expense': 'debit',
        'liability': 'credit',
        'equity': 'credit',
        'income': 'credit',
    }
    
    STANDARD_ACCOUNTS = [
        # Assets (1000-1999)
        ('1000', 'Cash', 'asset', True, 'USD'),
        ('1010', 'Petty Cash', 'asset', True, 'USD'),
        ('1100', 'Accounts Receivable', 'asset', True, 'USD'),
        ('1200', 'Inventory', 'asset', True, 'USD'),
        ('1300', 'Fixed Assets', 'asset', True, 'USD'),
        ('1310', 'Accumulated Depreciation', 'asset', True, 'USD'),
        
        # Liabilities (2000-2999)
        ('2000', 'Accounts Payable', 'liability', True, 'USD'),
        ('2100', 'Sales Tax Payable', 'liability', True, 'USD'),
        ('2110', 'VAT Payable', 'liability', True, 'USD'),
        ('2120', 'GST Payable', 'liability', True, 'USD'),
        ('2200', 'Accrued Expenses', 'liability', True, 'USD'),
        ('2300', 'Notes Payable', 'liability', True, 'USD'),
        
        # Equity (3000-3999)
        ('3000', "Owner's Equity", 'equity', True, 'USD'),
        ('3100', 'Retained Earnings', 'equity', True, 'USD'),
        ('3200', 'Drawings', 'equity', True, 'USD'),
        
        # Income (4000-4999)
        ('4000', 'Sales Revenue', 'income', True, 'USD'),
        ('4100', 'Service Revenue', 'income', True, 'USD'),
        ('4200', 'Discounts Given', 'income', True, 'USD'),
        ('4300', 'Interest Income', 'income', True, 'USD'),
        
        # Expenses (5000-5999)
        ('5000', 'Cost of Goods Sold', 'expense', True, 'USD'),
        ('5100', 'Salaries Expense', 'expense', True, 'USD'),
        ('5200', 'Rent Expense', 'expense', True, 'USD'),
        ('5300', 'Utilities Expense', 'expense', True, 'USD'),
        ('5400', 'Purchases', 'expense', True, 'USD'),
        ('5500', 'Purchase Discounts', 'expense', True, 'USD'),
        ('5600', 'Shipping Expense', 'expense', True, 'USD'),
        ('5700', 'Bank Charges', 'expense', True, 'USD'),
        ('5800', 'Depreciation Expense', 'expense', True, 'USD'),
        ('5900', 'Miscellaneous Expense', 'expense', True, 'USD'),
    ]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, help_text="System account - cannot be deleted")
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    opening_balance_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    description = models.TextField(blank=True)
    
    # Tax configuration
    is_taxable = models.BooleanField(default=False)
    
    # Bank details (for asset accounts of type bank)
    bank_name = models.CharField(max_length=255, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_routing_number = models.CharField(max_length=50, blank=True)
    bank_currency = models.CharField(max_length=3, blank=True, default='USD')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.opening_balance_date:
            self.opening_balance_date = timezone.now().date()
        super().save(*args, **kwargs)

    @property
    def normal_balance(self):
        """Get normal balance side for this account type"""
        return self.NORMAL_BALANCE.get(self.type, 'debit')

    @property
    def balance(self):
        """Calculate current account balance"""
        debits = JournalLine.objects.filter(
            account=self,
            debit_credit='debit'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        credits = JournalLine.objects.filter(
            account=self,
            debit_credit='credit'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        if self.normal_balance == 'debit':
            return self.opening_balance + debits - credits
        else:
            return self.opening_balance + credits - debits

    def balance_at_date(self, as_at_date):
        """Calculate account balance as at specific date"""
        debits = JournalLine.objects.filter(
            account=self,
            debit_credit='debit',
            journal_entry__entry_date__lte=as_at_date,
            journal_entry__is_posted=True
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        credits = JournalLine.objects.filter(
            account=self,
            debit_credit='credit',
            journal_entry__entry_date__lte=as_at_date,
            journal_entry__is_posted=True
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        if self.normal_balance == 'debit':
            return self.opening_balance + debits - credits
        else:
            return self.opening_balance + credits - debits


class AccountingSettings(models.Model):
    """
    Global accounting settings
    """
    TAX_SYSTEMS = [
        ('none', 'No Tax'),
        ('sales_tax', 'Sales Tax'),
        ('vat', 'Value Added Tax (VAT)'),
        ('gst', 'Goods & Services Tax (GST)'),
    ]
    
    DATE_FORMATS = [
        ('%Y-%m-%d', 'YYYY-MM-DD'),
        ('%d-%m-%Y', 'DD-MM-YYYY'),
        ('%m-%d-%Y', 'MM-DD-YYYY'),
    ]
    
    # Account mappings
    default_cash_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_ar_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_ap_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_inventory_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_sales_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_purchase_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_tax_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_cogs_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_shipping_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    default_discount_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='+', null=True)
    
    # Tax settings
    tax_system = models.CharField(max_length=20, choices=TAX_SYSTEMS, default='none')
    tax_inclusive_pricing = models.BooleanField(default=False)
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Fiscal settings
    fiscal_year_start_month = models.PositiveIntegerField(default=1, help_text="Month fiscal year starts (1-12)")
    fiscal_year_start_day = models.PositiveIntegerField(default=1, help_text="Day fiscal year starts (1-31)")
    
    # Numbering
    journal_entry_prefix = models.CharField(max_length=10, default='JE-')
    journal_entry_padding = models.PositiveIntegerField(default=5)
    journal_entry_next_number = models.PositiveIntegerField(default=1)
    
    # Features
    enable_multi_currency = models.BooleanField(default=False)
    enable_approval_workflow = models.BooleanField(default=False)
    enable_audit_trail = models.BooleanField(default=True)
    enable_budgeting = models.BooleanField(default=False)
    enable_auto_posting = models.BooleanField(default=True)
    
    # Display
    date_format = models.CharField(max_length=20, choices=DATE_FORMATS, default='%Y-%m-%d')
    show_running_balance = models.BooleanField(default=True)
    
    # Audit
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = "Accounting Settings"
        verbose_name_plural = "Accounting Settings"
    
    def clean(self):
        if not self.pk and AccountingSettings.objects.exists():
            raise ValidationError("Only one accounting settings instance can exist")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """Get or create default settings"""
        settings, created = cls.objects.get_or_create(
            defaults={
                'journal_entry_prefix': 'JE-',
                'journal_entry_padding': 5,
                'journal_entry_next_number': 1
            }
        )
        return settings
    
    def get_next_journal_number(self):
        """Get next journal entry number"""
        with transaction.atomic():
            settings = AccountingSettings.objects.select_for_update().get(pk=self.pk)
            number = settings.journal_entry_next_number
            settings.journal_entry_next_number += 1
            settings.save(update_fields=['journal_entry_next_number'])
            
            padded = str(number).zfill(self.journal_entry_padding)
            return f"{self.journal_entry_prefix}{padded}"


class ExchangeRate(models.Model):
    """
    Currency exchange rates for multi-currency support
    """
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    date = models.DateField(default=timezone.now)
    
    class Meta:
        unique_together = ['from_currency', 'to_currency', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.from_currency}→{self.to_currency}: {self.rate} on {self.date}"


class JournalEntry(models.Model):
    """
    General journal entries for double-entry accounting
    """
    JOURNAL_TYPES = [
        ('sale', 'Sales Journal'),
        ('purchase', 'Purchases Journal'),
        ('cash_receipt', 'Cash Receipts Journal'),
        ('cash_payment', 'Cash Payments Journal'),
        ('general', 'General Journal'),
    ]
    
    APPROVAL_STATUS = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('posted', 'Posted'),
    ]

    entry_number = models.CharField(max_length=50, unique=True, blank=True)
    journal_type = models.CharField(max_length=20, choices=JOURNAL_TYPES, default='general')
    entry_date = models.DateField(default=timezone.now)
    description = models.TextField()
    
    # Fiscal period
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, null=True, blank=True)
    period = models.ForeignKey(FiscalPeriod, on_delete=models.PROTECT, null=True, blank=True)
    
    # Status
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='draft')
    is_posted = models.BooleanField(default=False)
    
    # Approval tracking
    requires_approval = models.BooleanField(default=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_journal_entries'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_journal_entries'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_journal_entries'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Reference to source documents
    invoice = models.ForeignKey(
        Invoice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='journal_entries'
    )
    bill = models.ForeignKey(
        Bill,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='journal_entries'
    )
    payment = models.ForeignKey(
        Payment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='journal_entries'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_journal_entries'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='posted_journal_entries'
    )

    class Meta:
        ordering = ['-entry_date', '-id']
        verbose_name_plural = "Journal Entries"
        indexes = [
            models.Index(fields=['entry_number']),
            models.Index(fields=['journal_type']),
            models.Index(fields=['approval_status']),
            models.Index(fields=['entry_date']),
            models.Index(fields=['is_posted']),
        ]

    def __str__(self):
        return self.entry_number or f"JE-{self.id}"

    def save(self, *args, **kwargs):
        settings = AccountingSettings.get_settings()
        
        # Auto-generate entry number
        if not self.entry_number:
            self.entry_number = settings.get_next_journal_number()
        
        # Auto-set fiscal period (only if open)
        if not self.period and self.entry_date:
            self.period = FiscalPeriod.objects.filter(
                start_date__lte=self.entry_date,
                end_date__gte=self.entry_date,
                is_closed=False,
            ).first()

        super().save(*args, **kwargs)

    def clean(self):
        """Validate the journal entry"""
        if self.is_posted:
            raise ValidationError("Cannot modify posted journal entry")

        if self.approval_status in ['approved', 'rejected', 'posted'] and not self.pk:
            raise ValidationError("New entries cannot be approved/rejected/posted")

        if self.period and self.period.is_closed:
            raise ValidationError(f"Cannot create entries in closed period: {self.period}")

    def request_approval(self, user):
        """Request approval for this entry"""
        settings = AccountingSettings.get_settings()
        
        if not settings.enable_approval_workflow:
            return self.post(user)
        
        self.requires_approval = True
        self.approval_status = 'pending'
        self.requested_by = user
        self.save(update_fields=['requires_approval', 'approval_status', 'requested_by'])

    def approve(self, user):
        """Approve the journal entry"""
        if self.approval_status != 'pending':
            raise ValidationError("Only pending entries can be approved")
        
        self.approval_status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
        
        # Auto-post if configured
        settings = AccountingSettings.get_settings()
        if not settings.enable_approval_workflow:
            self.post(user)

    def reject(self, user, reason):
        """Reject the journal entry"""
        if self.approval_status != 'pending':
            raise ValidationError("Only pending entries can be rejected")
        
        self.approval_status = 'rejected'
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=['approval_status', 'rejected_by', 'rejected_at', 'rejection_reason'])

    def post(self, user=None):
        """Post the journal entry (make it permanent)"""
        if self.is_posted:
            raise ValidationError("Journal entry already posted")
        
        if self.approval_status not in ['approved', 'draft']:
            raise ValidationError(f"Cannot post entry with status: {self.approval_status}")
        
        # Verify debit = credit
        total_debits = self.lines.filter(debit_credit='debit').aggregate(total=Sum('amount'))['total'] or 0
        total_credits = self.lines.filter(debit_credit='credit').aggregate(total=Sum('amount'))['total'] or 0
        
        if abs(total_debits - total_credits) > Decimal('0.01'):  # Allow for floating point
            raise ValidationError(
                f"Debits ({total_debits}) must equal credits ({total_credits}). "
                f"Difference: {abs(total_debits - total_credits)}"
            )
        
        self.is_posted = True
        self.posted_by = user
        self.posted_at = timezone.now()
        self.approval_status = 'posted'
        self.save()
        
        # Create audit log if enabled
        settings = AccountingSettings.get_settings()
        if settings.enable_audit_trail:
            AuditLog.objects.create(
                user=user,
                action='POST',
                content_object=self,
                details=f"Posted journal entry {self.entry_number}"
            )

    @property
    def total_debits(self):
        return self.lines.filter(debit_credit='debit').aggregate(total=Sum('amount'))['total'] or 0
    
    @property
    def total_credits(self):
        return self.lines.filter(debit_credit='credit').aggregate(total=Sum('amount'))['total'] or 0


class JournalLine(models.Model):
    """
    Individual lines in a journal entry (debit/credit)
    """
    DEBIT_CREDIT_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='journal_lines',
        null=True,
        blank=True
    )
    account_code = models.CharField(max_length=20)  # Denormalized for performance
    account_name = models.CharField(max_length=100)  # Denormalized
    description = models.CharField(max_length=255, blank=True)
    debit_credit = models.CharField(max_length=10, choices=DEBIT_CREDIT_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # For multi-currency
    currency = models.CharField(max_length=3, default='USD')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1.0)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # For reconciliation
    is_reconciled = models.BooleanField(default=False)
    reconciled_date = models.DateField(null=True, blank=True)
    
    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['account', 'journal_entry']),
            models.Index(fields=['debit_credit']),
            models.Index(fields=['is_reconciled']),
        ]

    def __str__(self):
        return f"{self.journal_entry.entry_number} - {self.account_code} ({self.debit_credit}: {self.amount})"

    def save(self, *args, **kwargs):
        # Denormalize account info
        if self.account:
            self.account_code = self.account.code
            self.account_name = self.account.name
        
        # Calculate base amount if multi-currency
        if self.currency != 'USD' and self.exchange_rate != 1.0:
            self.base_amount = self.amount * self.exchange_rate
        else:
            self.base_amount = self.amount
        
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """
    Audit trail for all accounting transactions
    """
    ACTION_TYPES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('POST', 'Post'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
        ('VOID', 'Void'),
        ('RECONCILE', 'Reconcile'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Generic foreign key to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Old and new values (JSON)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    
    # Additional info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user']),
            models.Index(fields=['action']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.content_object} by {self.user} at {self.timestamp}"