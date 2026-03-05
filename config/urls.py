"""
URL configuration for ERP System.
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static
from products import views as product_views
from accounts.admin import erp_admin_site


def root_redirect(request):
    from setup.models import SetupStatus
    if not SetupStatus.is_complete():
        return redirect('setup:setup_welcome')
    return redirect('login')


urlpatterns = [
    # Root
    path('', root_redirect, name='root'),

    # Setup wizard
    path('setup/', include('setup.urls')),

    # Authentication (login / logout)
    path('', include('accounts.urls')),

    # ERP Admin (custom ERPAdminSite — must come before any other admin/ entries)
    path('admin/', erp_admin_site.urls),

    # Products custom views
    path('admin/products/setup/', product_views.product_setup, name='product_setup'),

    # ERP setup config (legacy erp-setup/ prefix)
    path('erp-setup/', include('config_settings.urls')),

    # Third-party
    path('select2/', include('django_select2.urls')),

    # App URLs
    path('products/', include('products.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('reports/', include('reports.urls')),
    path('core/', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
