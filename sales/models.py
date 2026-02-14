from django.db import models
from products.models import Product
from inventory.models import Stock

class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class SalesOrder(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
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
            stock = Stock.objects.filter(product=line.product).first()
            if not stock:
                raise ValueError(f"No stock found for {line.product}")

            stock.reduce_stock(
            line.quantity,
            reference=f"SalesOrder-{self.id}"
             )


    def save(self, *args, **kwargs):
        # Check previous status
        if self.pk:
            old_status = SalesOrder.objects.get(pk=self.pk).status
        else:
            old_status = None

        super().save(*args, **kwargs)

        # Trigger only if status changed to confirmed
        if old_status != 'confirmed' and self.status == 'confirmed':
            self.confirm_order()

    def __str__(self):
        return f"SO-{self.id} - {self.customer}"



class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product} x {self.quantity}"
