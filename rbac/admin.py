from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html, mark_safe

from .models import (
    AuditLog, ApprovalRule, Branch, Department,
    FieldPermission, ModulePermission, Role, UserProfile,
    MODULE_CHOICES,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Inline: ModulePermission inside Role
# ---------------------------------------------------------------------------

class ModulePermissionInline(admin.TabularInline):
    model = ModulePermission
    extra = 0
    fields = [
        'module', 'can_view', 'can_create', 'can_edit', 'can_delete',
        'can_approve', 'can_export', 'can_print', 'allowed_export_formats',
    ]
    ordering = ['module']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return len(MODULE_CHOICES)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('role')


class FieldPermissionInline(admin.TabularInline):
    model = FieldPermission
    extra = 0
    fields = ['module', 'field_name', 'can_view', 'can_edit']


# ---------------------------------------------------------------------------
# Role Admin
# ---------------------------------------------------------------------------

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'priority', 'is_active', 'is_system_role', 'user_count', 'updated_at']
    list_filter = ['is_active', 'is_system_role']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ModulePermissionInline, FieldPermissionInline]
    fieldsets = [
        (None, {'fields': ('name', 'code', 'priority', 'description')}),
        ('Status', {'fields': ('is_active', 'is_system_role')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    ]

    def user_count(self, obj):
        count = obj.users.count()
        if count:
            return format_html(
                '<span style="background:#366092;color:#fff;padding:2px 8px;border-radius:3px;">{}</span>',
                count,
            )
        return '—'
    user_count.short_description = 'Users'

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Invalidate cache for this role
        if form.instance.pk:
            from .services import PermissionService
            PermissionService.invalidate_role_cache(form.instance.pk)


# ---------------------------------------------------------------------------
# Department Admin
# ---------------------------------------------------------------------------

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['indented_name', 'code', 'head', 'member_count', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    raw_id_fields = ['head']

    def indented_name(self, obj):
        prefix = '&nbsp;&nbsp;&nbsp;&nbsp;' * (1 if obj.parent_id else 0)
        return mark_safe(f'{prefix}{obj.name}')
    indented_name.short_description = 'Department'
    indented_name.admin_order_field = 'name'

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


# ---------------------------------------------------------------------------
# Branch Admin
# ---------------------------------------------------------------------------

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'manager', 'is_main', 'is_active', 'warehouse_count']
    list_filter = ['is_active', 'is_main']
    search_fields = ['name', 'code', 'email']
    raw_id_fields = ['manager']
    filter_horizontal = ['warehouses']
    fieldsets = [
        (None, {'fields': ('name', 'code', 'is_main', 'is_active')}),
        ('Contact', {'fields': ('address', 'phone', 'email', 'manager')}),
        ('Warehouses', {'fields': ('warehouses',)}),
    ]

    def warehouse_count(self, obj):
        return obj.warehouses.count()
    warehouse_count.short_description = 'Warehouses'


# ---------------------------------------------------------------------------
# Approval Rule Admin
# ---------------------------------------------------------------------------

@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ['module', 'action', 'min_amount', 'required_approval_level', 'required_role', 'sequence', 'is_active']
    list_filter = ['module', 'is_active']
    search_fields = ['module', 'action', 'description']
    list_editable = ['sequence', 'is_active']
    fieldsets = [
        (None, {'fields': ('module', 'action', 'description')}),
        ('Conditions', {'fields': ('min_amount', 'required_approval_level', 'required_role')}),
        ('Configuration', {'fields': ('sequence', 'is_active')}),
    ]


# ---------------------------------------------------------------------------
# UserProfile Inline (inside User admin)
# ---------------------------------------------------------------------------

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = 'ERP Profile'
    verbose_name_plural = 'ERP Profile'
    extra = 1
    filter_horizontal = ['warehouses']
    fieldsets = [
        ('Organization', {
            'fields': ('role', 'department', 'branch', 'employee_id', 'phone'),
        }),
        ('Warehouse Access', {
            'fields': ('warehouses',),
            'description': 'Leave empty to allow access to all warehouses.',
        }),
        ('Approval Authority', {
            'fields': ('approval_level',),
        }),
        ('Working Hours', {
            'fields': ('work_start', 'work_end', 'work_days'),
            'description': 'Restrict login to specific hours/days. Leave blank for no restriction.',
            'classes': ('collapse',),
        }),
        ('Account Lock', {
            'fields': ('failed_login_attempts', 'locked_until', 'last_password_change'),
            'classes': ('collapse',),
        }),
    ]


# CustomUser is registered in accounts/admin.py (CustomUserAdmin with UserProfileInline)


# ---------------------------------------------------------------------------
# Audit Log Admin (read-only)
# ---------------------------------------------------------------------------

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'user_link', 'action_badge', 'module', 'model_name',
        'object_link', 'ip_address',
    ]
    list_filter = ['action', 'module', 'model_name']
    search_fields = ['user__username', 'object_repr', 'object_id', 'module', 'ip_address']
    date_hierarchy = 'timestamp'
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_system_admin

    def user_link(self, obj):
        if obj.user:
            return format_html(
                '<a href="/admin/accounts/customuser/{}/change/">{}</a>',
                obj.user.pk, obj.user.username,
            )
        return '—'
    user_link.short_description = 'User'

    def action_badge(self, obj):
        colors = {
            'create': ('#28a745', '#fff'),
            'update': ('#007bff', '#fff'),
            'delete': ('#dc3545', '#fff'),
            'login': ('#17a2b8', '#fff'),
            'logout': ('#6c757d', '#fff'),
            'export': ('#fd7e14', '#fff'),
            'approve': ('#28a745', '#fff'),
            'reject': ('#dc3545', '#fff'),
            'print': ('#6f42c1', '#fff'),
            'lock': ('#dc3545', '#fff'),
        }
        bg, fg = colors.get(obj.action, ('#999', '#fff'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:3px;font-size:11px;font-weight:bold">{}</span>',
            bg, fg, obj.get_action_display(),
        )
    action_badge.short_description = 'Action'
    action_badge.admin_order_field = 'action'

    def object_link(self, obj):
        if obj.object_repr:
            return format_html(
                '<span title="ID: {}">{}</span>',
                obj.object_id, obj.object_repr,
            )
        return obj.object_id or '—'
    object_link.short_description = 'Object'


# ---------------------------------------------------------------------------
# UserProfile Admin (standalone for superuser inspection)
# ---------------------------------------------------------------------------

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'branch', 'approval_level', 'is_locked_badge', 'work_hours_display']
    list_filter = ['role', 'department', 'branch']
    search_fields = ['user__username', 'user__email', 'employee_id']
    raw_id_fields = ['user']
    filter_horizontal = ['warehouses']
    readonly_fields = ['failed_login_attempts', 'locked_until', 'last_password_change']

    fieldsets = [
        ('User', {'fields': ('user', 'employee_id', 'phone')}),
        ('Organization', {'fields': ('role', 'department', 'branch')}),
        ('Warehouse Access', {'fields': ('warehouses',)}),
        ('Approval Authority', {'fields': ('approval_level',)}),
        ('Working Hours', {
            'fields': ('work_start', 'work_end', 'work_days'),
            'classes': ('collapse',),
        }),
        ('Account Lock', {
            'fields': ('failed_login_attempts', 'locked_until', 'last_password_change'),
            'classes': ('collapse',),
        }),
    ]

    def is_locked_badge(self, obj):
        if obj.is_locked():
            return mark_safe(
                '<span style="background:#dc3545;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px">LOCKED</span>'
            )
        return mark_safe('<span style="color:#28a745">Active</span>')
    is_locked_badge.short_description = 'Status'

    def work_hours_display(self, obj):
        if obj.work_start and obj.work_end:
            return f'{obj.work_start:%H:%M} – {obj.work_end:%H:%M} ({obj.get_work_days_display()})'
        return '—'
    work_hours_display.short_description = 'Work Hours'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .services import PermissionService
        PermissionService.invalidate_user_cache(obj.user_id)
