# inventory/mixins.py
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class DashboardMixin:
    """Mixin for inventory admin classes"""
    
    def get_dashboard_context(self, request):
        """Get common dashboard context"""
        from .dashboard import InventoryDashboard
        return InventoryDashboard.get_metrics()
    
    def changelist_view(self, request, extra_context=None):
        """Add dashboard metrics to changelist view"""
        extra_context = extra_context or {}
        extra_context['dashboard_metrics'] = self.get_dashboard_context(request)
        return super().changelist_view(request, extra_context=extra_context)