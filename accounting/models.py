from django.db import models
from sales.models import SalesOrder
from purchasing.models import PurchaseOrder


class Invoice(models.Model):
    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.CASCADE
    )
    invoice_date = models.DateField(auto_now_add=True)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    paid = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Auto calculate total
        total = 0
        for line in self.sales_order.lines.all():
            total += line.quantity * line.price

        self.total_amount = total
        super().save(update_fields=['total_amount'])

    def __str__(self):
        return f"INV-{self.id}"



class Bill(models.Model):
    purchase_order = models.OneToOneField(
        PurchaseOrder,
        on_delete=models.CASCADE
    )
    bill_date = models.DateField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.BooleanField(default=False)

    def calculate_total(self):
        total = 0
        for line in self.purchase_order.lines.all():
            total += line.quantity * line.price
        self.total_amount = total
        self.save()

    def __str__(self):
        return f"BILL-{self.id}"


class Payment(models.Model):
    PAYMENT_TYPE = [
        ('customer', 'Customer Payment'),
        ('vendor', 'Vendor Payment'),
    ]

    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE)
    invoice = models.ForeignKey(
        Invoice,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )
    bill = models.ForeignKey(
        Bill,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Payment-{self.id}"
