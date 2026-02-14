from django.contrib import admin
from .models import Invoice, Bill, Payment

admin.site.register(Invoice)
admin.site.register(Bill)
admin.site.register(Payment)
