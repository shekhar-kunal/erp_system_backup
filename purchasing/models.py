from django.db import models
from products.models import Product
from inventory.models import Stock, Warehouse


class Vendor(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    order_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
        ],
        default='draft'
    )

    def confirm_order(self):
        if self.status != 'confirmed':
            return

        for line in self.lines.all():
            stock, created = Stock.objects.get_or_create(
            product=line.product,
            warehouse=self.warehouse,
            defaults={'quantity': 0}
            )

            stock.increase_stock(
            line.quantity,
            reference=f"PurchaseOrder-{self.id}"
            )

    def save(self, *args, **kwargs):
        if self.pk:
            old_status = PurchaseOrder.objects.get(pk=self.pk).status
        else:
            old_status = None

        super().save(*args, **kwargs)

        if old_status != 'confirmed' and self.status == 'confirmed':
            self.confirm_order()

    def __str__(self):
        return f"PO-{self.id} - {self.vendor}"


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product} x {self.quantity}"
