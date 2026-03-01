from django.shortcuts import redirect
from django.urls import reverse
from .models import ERPSettings

class ERPSetupMiddleware:
    """Redirect to setup wizard if ERP not configured"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip for admin login, setup page, and static files
        if request.path.startswith('/admin/login/') or \
           request.path.startswith('/erp-setup/') or \
           request.path.startswith('/static/'):
            return self.get_response(request)
        
        # Check if ERP is configured
        if request.path.startswith('/admin/'):
            settings = ERPSettings.get_settings()
            if not settings.setup_completed:
                return redirect('erp_setup')
        
        return self.get_response(request)