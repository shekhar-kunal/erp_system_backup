from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AdminPasswordChangeForm
from django.shortcuts import redirect
from django import forms
from django.utils.html import format_html

from .models import CustomUser


# ---------------------------------------------------------------------------
# Custom Admin Site
# ---------------------------------------------------------------------------

class ERPAdminSite(AdminSite):
    site_header = 'ERP Administration'
    site_title  = 'ERP Admin'
    index_title = 'System Dashboard'
    login_url   = '/login/'

    def has_permission(self, request):
        """
        Grant admin access to:
        - System admins (is_system_admin=True), or
        - Any user with an active RBAC role.
        Replaces Django's default is_active + is_staff check.
        """
        if not request.user.is_authenticated:
            return False
        if not request.user.is_active:
            return False
        if request.user.is_system_admin:
            return True
        try:
            from rbac.services import PermissionService
            profile = PermissionService._get_profile(request.user)
            return bool(profile and profile.role and profile.role.is_active)
        except Exception:
            return False

    def login(self, request, extra_context=None):
        """Redirect unauthenticated requests to the custom login page."""
        next_url = request.GET.get('next', '/admin/')
        return redirect(f'/login/?next={next_url}')


# Singleton — name='admin' keeps all {% url 'admin:...' %} template tags working
erp_admin_site = ERPAdminSite(name='admin')


# ---------------------------------------------------------------------------
# Custom forms for CustomUser
# ---------------------------------------------------------------------------

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model  = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_system_admin')


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model  = CustomUser
        fields = '__all__'


# ---------------------------------------------------------------------------
# CustomUser Admin
# ---------------------------------------------------------------------------

class CustomUserAdmin(admin.ModelAdmin):
    form             = CustomUserChangeForm
    add_form         = CustomUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display  = [
        'username', 'email', 'get_full_name', 'is_active',
        'is_system_admin', 'get_role', 'get_branch', 'date_joined',
    ]
    list_filter   = ['is_active', 'is_system_admin']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering      = ['username']
    readonly_fields = ['date_joined', 'last_login']

    fieldsets = [
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Access', {'fields': ('is_active', 'is_system_admin')}),
        ('Timestamps', {
            'fields': ('date_joined', 'last_login'),
            'classes': ('collapse',),
        }),
    ]
    add_fieldsets = [
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'first_name', 'last_name',
                'password1', 'password2', 'is_active', 'is_system_admin',
            ),
        }),
    ]

    def get_form(self, request, obj=None, **kwargs):
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_inline_instances(self, request, obj=None):
        # Import UserProfileInline lazily to avoid circular import
        from rbac.admin import UserProfileInline
        inlines = [UserProfileInline(self.model, self.admin_site)]
        return inlines if obj else []

    def get_role(self, obj):
        try:
            role = obj.profile.role
            if role:
                return format_html(
                    '<span style="background:#2d3561;color:#fff;padding:2px 8px;'
                    'border-radius:3px;font-size:11px;font-weight:600">{}</span>',
                    role.name,
                )
        except Exception:
            pass
        return '—'
    get_role.short_description = 'Role'

    def get_branch(self, obj):
        try:
            return obj.profile.branch.name if obj.profile.branch else '—'
        except Exception:
            return '—'
    get_branch.short_description = 'Branch'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            from rbac.services import PermissionService
            PermissionService.invalidate_user_cache(obj.pk)
        except Exception:
            pass


erp_admin_site.register(CustomUser, CustomUserAdmin)
