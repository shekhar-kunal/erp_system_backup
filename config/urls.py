"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from products import views as product_views

urlpatterns = [
    # Custom admin URLs must come BEFORE admin.site.urls
    path('admin/products/setup/', product_views.product_setup, name='product_setup'),

    path('erp-setup/', include('config_settings.urls')),

    path('select2/', include('django_select2.urls')),
    path('products/', include('products.urls')),

    # Central dashboard (role-based) — single include under /dashboard/
    path('dashboard/', include('dashboard.urls')),
    path('reports/', include('reports.urls')),
    # Root redirect to dashboard home
    path('', RedirectView.as_view(url='/dashboard/', permanent=False), name='home'),
    path('core/', include('core.urls')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)