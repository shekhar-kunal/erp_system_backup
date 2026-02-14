from django.contrib import admin
from .models import Customer, SalesOrder, SalesOrderLine


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == 'confirmed':
            return False
        return True

    def has_add_permission(self, request, obj):
        if obj and obj.status == 'confirmed':
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == 'confirmed':
            return False
        return True


class SalesOrderAdmin(admin.ModelAdmin):
    inlines = [SalesOrderLineInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == 'confirmed':
            return [field.name for field in self.model._meta.fields]
        return []


admin.site.register(Customer)
admin.site.register(SalesOrder, SalesOrderAdmin)
