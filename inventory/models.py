from django.db import models
from products.models import Product


class Warehouse(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Stock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ('product', 'warehouse')

    def increase_stock(self, qty, reference=""):
        self.quantity += qty
        self.save()

        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type='in',
            quantity=qty,
            reference=reference
        )

    def reduce_stock(self, qty, reference=""):
        if self.quantity < qty:
            raise ValueError("Not enough stock available")

        self.quantity -= qty
        self.save()

        StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            movement_type='out',
            quantity=qty,
            reference=reference
        )

    def __str__(self):
        return f"{self.product} @ {self.warehouse}"


class StockMovement(models.Model):
    MOVEMENT_TYPE = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_TYPE)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product} - {self.movement_type} - {self.quantity}"
