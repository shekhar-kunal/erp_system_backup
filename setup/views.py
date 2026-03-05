from django.shortcuts import render, redirect
from django.views.generic import TemplateView, FormView
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import login
from decimal import Decimal
import logging


def _to_json(data):
    """Convert form cleaned_data values to JSON-serializable types."""
    result = {}
    for key, val in data.items():
        if isinstance(val, Decimal):
            result[key] = str(val)
        elif hasattr(val, 'code') and hasattr(val, 'pk'):  # Currency / code-keyed model
            result[key] = val.code
        elif hasattr(val, 'pk'):          # generic model instance
            result[key] = val.pk
        else:
            result[key] = val
    return result

from .models import SetupStatus, InstallationLog
from .forms import (
    WelcomeForm, CompanyForm, AdminUserForm,
    ModulesForm, ConfigurationForm, ReviewForm
)
from accounts.models import CustomUser
from config_settings.models import CompanyProfile, Currency, ERPSettings
from rbac.models import Role, Department

logger = logging.getLogger(__name__)


class SetupBaseView(TemplateView):
    """Base view for setup wizard"""
    template_name = 'setup/base_setup.html'
    step = 1
    total_steps = 8

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['step'] = self.step
        context['total_steps'] = self.total_steps
        context['progress_percent'] = int((self.step / self.total_steps) * 100)
        return context

    def get_setup_status(self):
        status, created = SetupStatus.objects.get_or_create(pk=1)
        return status


class WelcomeView(SetupBaseView, FormView):
    """Step 1: Welcome & Language"""
    template_name = 'setup/welcome.html'
    form_class = WelcomeForm
    success_url = reverse_lazy('setup:setup_company')
    step = 1

    def get_initial(self):
        status = self.get_setup_status()
        data = status.get_step_data('welcome')
        initial = {
            'language': data.get('language', 'en'),
            'country': data.get('country', 'US'),
            'timezone': data.get('timezone', 'America/New_York'),
            'date_format': data.get('date_format', 'Y-m-d'),
        }
        # Restore currency from stored code string → Currency instance
        currency_code = data.get('currency')
        if currency_code:
            try:
                initial['currency'] = Currency.objects.get(code=currency_code)
            except Currency.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        status = self.get_setup_status()
        status.save_step_data('welcome', _to_json(form.cleaned_data))
        status.current_step = 2
        status.save()

        InstallationLog.objects.create(
            step='welcome',
            level='success',
            message='Welcome step completed'
        )

        return super().form_valid(form)


class CompanyView(SetupBaseView, FormView):
    """Step 2: Company Information"""
    template_name = 'setup/company.html'
    form_class = CompanyForm
    success_url = reverse_lazy('setup:setup_admin')
    step = 2

    def get_initial(self):
        status = self.get_setup_status()
        return status.get_step_data('company')

    def form_valid(self, form):
        status = self.get_setup_status()
        status.save_step_data('company', _to_json(form.cleaned_data))
        status.current_step = 3
        status.save()

        InstallationLog.objects.create(
            step='company',
            level='success',
            message='Company information saved'
        )

        return super().form_valid(form)


class AdminUserView(SetupBaseView, FormView):
    """Step 3: Create Admin User"""
    template_name = 'setup/admin.html'
    form_class = AdminUserForm
    success_url = reverse_lazy('setup:setup_modules')
    step = 3

    def get_initial(self):
        status = self.get_setup_status()
        return status.get_step_data('admin')

    def form_valid(self, form):
        status = self.get_setup_status()
        # Don't save password in plain text
        data = _to_json(form.cleaned_data)
        data.pop('password', None)
        data.pop('confirm_password', None)
        status.save_step_data('admin', data)
        # Store password separately (will be hashed during installation)
        status.setup_data['admin_password'] = form.cleaned_data['password']
        status.current_step = 4
        status.save()

        InstallationLog.objects.create(
            step='admin',
            level='success',
            message=f"Admin user {data['username']} configured"
        )

        return super().form_valid(form)


class ModulesView(SetupBaseView, FormView):
    """Step 4: Module Selection"""
    template_name = 'setup/modules.html'
    form_class = ModulesForm
    success_url = reverse_lazy('setup:setup_configure')
    step = 4

    def get_initial(self):
        status = self.get_setup_status()
        return status.get_step_data('modules')

    def form_valid(self, form):
        status = self.get_setup_status()
        status.save_step_data('modules', _to_json(form.cleaned_data))
        status.current_step = 5
        status.save()

        InstallationLog.objects.create(
            step='modules',
            level='success',
            message=f"Selected {len(form.cleaned_data['modules'])} modules"
        )

        return super().form_valid(form)


class ConfigureView(SetupBaseView, FormView):
    """Step 5: System Configuration"""
    template_name = 'setup/configure.html'
    form_class = ConfigurationForm
    success_url = reverse_lazy('setup:setup_review')
    step = 5

    def get_initial(self):
        status = self.get_setup_status()
        return status.get_step_data('configure')

    def form_valid(self, form):
        status = self.get_setup_status()
        status.save_step_data('configure', _to_json(form.cleaned_data))
        status.current_step = 6
        status.save()

        InstallationLog.objects.create(
            step='configure',
            level='success',
            message='System configuration saved'
        )

        return super().form_valid(form)


class ReviewView(SetupBaseView, FormView):
    """Step 6: Review & Confirm"""
    template_name = 'setup/review.html'
    form_class = ReviewForm
    success_url = reverse_lazy('setup:setup_install')
    step = 6

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.get_setup_status()

        context['welcome_data'] = status.get_step_data('welcome')
        context['company_data'] = status.get_step_data('company')
        context['admin_data'] = status.get_step_data('admin')
        context['modules_data'] = status.get_step_data('modules')
        context['configure_data'] = status.get_step_data('configure')

        return context

    def form_valid(self, form):
        status = self.get_setup_status()
        status.current_step = 7
        status.save()

        InstallationLog.objects.create(
            step='review',
            level='success',
            message='Installation confirmed'
        )

        return super().form_valid(form)


class InstallView(SetupBaseView, TemplateView):
    """Step 7: Installation Progress"""
    template_name = 'setup/install.html'
    step = 7

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)

        try:
            self.run_installation(request)
            context['installation_started'] = True
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            InstallationLog.objects.create(
                step='install',
                level='error',
                message=f"Installation failed: {str(e)}"
            )
            context['error'] = str(e)

        return self.render_to_response(context)

    def run_installation(self, request):
        """Run the actual installation"""
        status = SetupStatus.objects.get(pk=1)

        with transaction.atomic():
            # Step 1: Create Company Profile
            InstallationLog.objects.create(step='install', message='Creating company profile...')
            company_data = status.get_step_data('company')

            full_address = '\n'.join(filter(None, [
                company_data.get('address_line1', ''),
                company_data.get('address_line2', ''),
                f"{company_data.get('city', '')}, {company_data.get('state', '')} {company_data.get('postal_code', '')}".strip(', '),
                company_data.get('country', ''),
            ]))

            company, _ = CompanyProfile.objects.get_or_create(pk=1)
            company.name = company_data['company_name']
            company.tax_id = company_data.get('tax_id', '')
            company.registration_number = company_data.get('registration_number', '')
            company.address = full_address
            company.phone = company_data['phone']
            company.email = company_data['email']
            company.website = company_data.get('website', '')
            company.save()
            status.company_id = company.pk
            status.save()

            # Step 2: Create Default Roles
            InstallationLog.objects.create(step='install', message='Creating default roles...')
            self.create_default_roles()

            # Step 3: Create Admin User
            InstallationLog.objects.create(step='install', message='Creating admin user...')
            admin_data = status.get_step_data('admin')
            admin_password = status.setup_data.get('admin_password')

            admin_user = CustomUser.objects.create_user(
                username=admin_data['username'],
                email=admin_data['email'],
                password=admin_password,
                first_name=admin_data['first_name'],
                last_name=admin_data['last_name'],
                is_system_admin=True,
            )
            status.admin_user_id = admin_user.id
            status.save()

            # Assign admin role via UserProfile
            from rbac.models import UserProfile
            admin_role = Role.objects.get(code='admin_erp')
            UserProfile.objects.get_or_create(
                user=admin_user,
                defaults={'role': admin_role}
            )

            # Step 4: Configure ERP Settings
            InstallationLog.objects.create(step='install', message='Configuring system settings...')
            welcome_data = status.get_step_data('welcome')
            configure_data = status.get_step_data('configure')

            currency_code = welcome_data.get('currency', 'USD')
            try:
                currency = Currency.objects.get(code=currency_code)
            except Currency.DoesNotExist:
                currency = Currency.objects.first()

            erp_settings, _ = ERPSettings.objects.get_or_create(pk=1)
            erp_settings.default_currency = currency
            erp_settings.date_format = welcome_data.get('date_format', 'Y-m-d')
            erp_settings.timezone_name = welcome_data.get('timezone', 'UTC')
            erp_settings.allow_negative_inventory = configure_data.get('allow_negative_stock', False)
            erp_settings.setup_completed = True
            erp_settings.save()

            # Step 5: Install Selected Modules
            modules_data = status.get_step_data('modules')
            selected_modules = modules_data.get('modules', [])

            InstallationLog.objects.create(
                step='install',
                message=f"Installing {len(selected_modules)} modules..."
            )

            from config_settings.models import ModuleStatus
            for module_code in selected_modules:
                ModuleStatus.objects.get_or_create(
                    module=module_code,
                    defaults={'is_enabled': True}
                )

            # Step 6: Load Sample Data if requested
            if modules_data.get('install_sample_data'):
                InstallationLog.objects.create(step='install', message='Loading sample data...')
                self.create_sample_data()

            # Step 7: Mark installation complete
            InstallationLog.objects.create(step='install', message='Installation complete!')
            status.completed = True
            status.completed_at = timezone.now()
            status.current_step = 8
            status.save()

            # Auto-login the admin user
            login(request, admin_user)

    def create_default_roles(self):
        """Create default RBAC roles"""
        roles = [
            {'code': 'admin_erp', 'name': 'ERP Administrator', 'is_system_role': True},
            {'code': 'finance_mgr', 'name': 'Finance Manager', 'is_system_role': True},
            {'code': 'sales_mgr', 'name': 'Sales Manager', 'is_system_role': True},
            {'code': 'purchase_mgr', 'name': 'Purchase Manager', 'is_system_role': True},
            {'code': 'inventory_mgr', 'name': 'Inventory Manager', 'is_system_role': True},
            {'code': 'employee', 'name': 'Employee', 'is_system_role': True},
        ]

        for role_data in roles:
            Role.objects.get_or_create(
                code=role_data['code'],
                defaults=role_data
            )

    def create_sample_data(self):
        """Create sample data for demo"""
        from products.models import ProductCategory
        from sales.models import Customer
        from core.models import Country, City

        # Create sample categories
        for cat_name in ['Electronics', 'Furniture', 'Office Supplies']:
            slug = cat_name.lower().replace(' ', '-')
            if not ProductCategory.objects.filter(slug=slug).exists():
                ProductCategory.objects.create(name=cat_name, slug=slug)

        # Ensure Country + City exist (billing_city is a FK, not a plain string)
        country = Country.objects.filter(is_active=True).first()
        if not country:
            country, _ = Country.objects.get_or_create(
                code='USA',
                defaults={'name': 'United States', 'iso_code': 'US', 'is_active': True}
            )
        city, _ = City.objects.get_or_create(
            name='New York',
            country=country,
            defaults={'state': 'NY'}
        )

        Customer.objects.get_or_create(
            email='contact@abccorp.com',
            defaults={
                'customer_type': 'business',
                'company_name': 'ABC Corp',
                'phone': '+1-555-0123',
                'billing_address_line1': '123 Business Ave',
                'billing_country': country,
                'billing_city': city,
                'billing_postal_code': '10001',
            }
        )


class CompleteView(SetupBaseView, TemplateView):
    """Step 8: Installation Complete"""
    template_name = 'setup/complete.html'
    step = 8

    def get(self, request, *args, **kwargs):
        try:
            status = SetupStatus.objects.get(pk=1)
        except SetupStatus.DoesNotExist:
            return redirect('setup:setup_welcome')

        if not status.completed:
            return redirect('setup:setup_welcome')

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = SetupStatus.objects.get(pk=1)

        context['company'] = CompanyProfile.objects.get(pk=status.company_id)
        context['admin_user'] = CustomUser.objects.get(pk=status.admin_user_id)
        context['modules'] = status.get_step_data('modules').get('modules', [])

        return context
