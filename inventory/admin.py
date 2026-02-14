from django.contrib import admin
from .models import Warehouse, Stock
from .models import StockMovement


admin.site.register(Warehouse)
admin.site.register(Stock)
admin.site.register(StockMovement)
