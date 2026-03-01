from django import forms
from django.contrib import admin
from django.utils.html import format_html, mark_safe

from .models import ExportConfig, ExportLog, UserExportPreference, FORMAT_CHOICES, MODULE_CHOICES


# ---------------------------------------------------------------------------
# ExportConfig
# ---------------------------------------------------------------------------

class ExportConfigForm(forms.ModelForm):
    """
    Uses CheckboxSelectMultiple for enabled_formats so admins can tick individual formats.
    """
    FORMAT_CHOICES_FOR_WIDGET = [
        (k, v) for k, v in FORMAT_CHOICES if k != 'none'
    ]
    enabled_formats = forms.MultipleChoiceField(
        choices=FORMAT_CHOICES_FOR_WIDGET,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text='Select which export formats are available for this module.',
    )

    class Meta:
        model = ExportConfig
        fields = '__all__'

    def clean_enabled_formats(self):
        return list(self.cleaned_data.get('enabled_formats', []))


@admin.register(ExportConfig)
class ExportConfigAdmin(admin.ModelAdmin):
    form = ExportConfigForm
    list_display = [
        'module_key_display', 'enabled_formats_display',
        'default_format', 'max_rows', 'is_active', 'updated_at',
    ]
    list_filter = ['is_active', 'default_format']
    search_fields = ['module_key']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('Module', {
            'fields': ('module_key', 'is_active'),
        }),
        ('Enabled Formats', {
            'fields': ('enabled_formats', 'default_format'),
        }),
        ('Default Export Options', {
            'fields': (
                'include_headers_default',
                'include_footer_default',
                'compress_zip_default',
                'date_format_default',
            ),
        }),
        ('Limits & Permissions', {
            'fields': ('max_rows', 'require_staff'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    ]

    def module_key_display(self, obj):
        return obj.get_module_key_display()
    module_key_display.short_description = 'Module'
    module_key_display.admin_order_field = 'module_key'

    def enabled_formats_display(self, obj):
        fmts = obj.enabled_formats or []
        if not fmts:
            return format_html('<span style="color:#999">— none —</span>')
        badges = ''.join(
            f'<span style="background:#366092;color:#fff;padding:1px 6px;border-radius:3px;'
            f'font-size:11px;margin-right:3px">{f.upper()}</span>'
            for f in fmts
        )
        return mark_safe(badges)
    enabled_formats_display.short_description = 'Enabled Formats'

    def has_module_perms(self, app_label):
        # Only superusers can manage export configurations
        return self.request.user.is_superuser if hasattr(self, 'request') else True

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ---------------------------------------------------------------------------
# ExportLog
# ---------------------------------------------------------------------------

@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'user', 'module_key', 'export_format',
        'status_badge', 'record_count', 'file_size_display', 'duration_display',
    ]
    list_filter = ['status', 'export_format', 'module_key']
    search_fields = ['user__username', 'module_key', 'filename', 'ip_address']
    date_hierarchy = 'created_at'
    readonly_fields = [f.name for f in ExportLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def status_badge(self, obj):
        colors = {
            'success': ('#28a745', '#fff'),
            'failed': ('#dc3545', '#fff'),
            'partial': ('#ffc107', '#000'),
            'cancelled': ('#6c757d', '#fff'),
        }
        bg, fg = colors.get(obj.status, ('#999', '#fff'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:3px;'
            'font-size:11px;font-weight:bold">{}</span>',
            bg, fg, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def file_size_display(self, obj):
        if obj.file_size_bytes:
            if obj.file_size_bytes >= 1_048_576:
                return f"{obj.file_size_bytes / 1_048_576:.1f} MB"
            elif obj.file_size_bytes >= 1024:
                return f"{obj.file_size_bytes / 1024:.1f} KB"
            return f"{obj.file_size_bytes} B"
        return "—"
    file_size_display.short_description = 'File Size'

    def duration_display(self, obj):
        if obj.duration_ms:
            if obj.duration_ms >= 1000:
                return f"{obj.duration_ms / 1000:.1f}s"
            return f"{obj.duration_ms}ms"
        return "—"
    duration_display.short_description = 'Duration'


# ---------------------------------------------------------------------------
# UserExportPreference
# ---------------------------------------------------------------------------

@admin.register(UserExportPreference)
class UserExportPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'module_key', 'preferred_format', 'include_headers', 'compress_zip', 'date_format']
    list_filter = ['preferred_format', 'module_key']
    search_fields = ['user__username', 'module_key']
    raw_id_fields = ['user']

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Users can only see their own, superusers see all
        if obj is not None and not request.user.is_superuser:
            return obj.user == request.user
        return True

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            return obj.user == request.user
        return True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)
