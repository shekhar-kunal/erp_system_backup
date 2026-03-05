"""
ConfigurableExportMixin
=======================
Drop-in replacement for ExcelExportMixin (products/admin.py).

Usage in any ModelAdmin:

    from exports.mixins import ConfigurableExportMixin

    @admin.register(MyModel)
    class MyModelAdmin(ConfigurableExportMixin, admin.ModelAdmin):
        export_fields = ['name', 'price', 'category__name']
        export_methods = {
            'is_active': lambda obj: 'Yes' if obj.is_active else 'No',
        }

The mixin:
- Reads ExportConfig to know which formats are enabled for this model.
- Dynamically injects export actions into the changelist (one per enabled format).
- On action: stores selected PKs in the session, redirects to an options page.
- Options page lets the user choose format + options (headers, footer, zip, date format).
- After form submit: runs the appropriate backend, writes ExportLog, returns file response.
"""
import time
import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

logger = logging.getLogger(__name__)


def _has_rbac_role(user):
    """Return True if user has system admin access or an active RBAC role."""
    if getattr(user, 'is_system_admin', False):
        return True
    try:
        from rbac.services import PermissionService
        profile = PermissionService._get_profile(user)
        return bool(profile and profile.role and profile.role.is_active)
    except Exception:
        return True  # fail open


class ConfigurableExportMixin:
    """
    Inherits the same export_fields / export_methods attributes as ExcelExportMixin
    but routes all export actions through a centralized configuration system.
    """

    # Subclass can set this to False to skip the options page and use defaults/prefs directly.
    export_show_options_page: bool = True

    # ----------------------------------------------------------------
    # Module key
    # ----------------------------------------------------------------

    def get_module_key(self) -> str:
        return f"{self.model._meta.app_label}.{self.model._meta.model_name}"

    # ----------------------------------------------------------------
    # Config + preferences
    # ----------------------------------------------------------------

    def get_export_config(self):
        from exports.models import ExportConfig
        return ExportConfig.get_for_model(
            self.model._meta.app_label,
            self.model._meta.model_name,
        )

    def get_user_preference(self, user):
        from exports.models import UserExportPreference
        try:
            return UserExportPreference.objects.get(
                user=user,
                module_key=self.get_module_key(),
            )
        except UserExportPreference.DoesNotExist:
            return None

    def get_effective_options(self, user, form_data=None) -> dict:
        """
        Resolve export options in priority order:
          1. form_data (from options page POST, highest priority)
          2. user preference record
          3. ExportConfig defaults (lowest priority)
        """
        config = self.get_export_config()
        pref = self.get_user_preference(user)

        options = {
            'format': pref.preferred_format if pref else config.default_format,
            'include_headers': pref.include_headers if pref else config.include_headers_default,
            'include_footer': pref.include_footer if pref else config.include_footer_default,
            'compress_zip': pref.compress_zip if pref else config.compress_zip_default,
            'date_format': pref.date_format if pref else config.date_format_default,
        }
        if form_data:
            options.update({k: v for k, v in form_data.items() if v is not None})
        return options

    # ----------------------------------------------------------------
    # Dynamic action registration
    # ----------------------------------------------------------------

    def get_actions(self, request):
        actions = super().get_actions(request)
        config = self.get_export_config()

        if not config.is_active:
            return actions
        if config.require_staff and not _has_rbac_role(request.user):
            return actions

        # RBAC: check module-level export permission and allowed formats
        try:
            from rbac.services import PermissionService
            if not PermissionService.has_module_permission(request.user, self.get_module_key(), 'export'):
                return actions
            allowed_formats = PermissionService.get_allowed_export_formats(request.user, self.get_module_key())
        except Exception:
            allowed_formats = None  # rbac not available — fall back to unrestricted

        for fmt in config.enabled_formats:
            if fmt in ('none', 'google_sheets'):
                continue
            # None = all formats allowed; list = only those formats
            if allowed_formats is not None and fmt not in allowed_formats:
                continue
            action_func = self._make_export_action(fmt)
            action_name = f'export_as_{fmt}'
            actions[action_name] = (action_func, action_name, f"Export selected as {fmt.upper()}")

        return actions

    def _make_export_action(self, fmt: str):
        def action(modeladmin, request, queryset):
            return modeladmin._redirect_to_options_page(request, queryset, fmt)

        action.__name__ = f'export_as_{fmt}'
        action.short_description = f"Export selected as {fmt.upper()}"
        return action

    # ----------------------------------------------------------------
    # URL registration
    # ----------------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        custom = [
            path(
                'export-options/',
                self.admin_site.admin_view(self.export_options_view),
                name=f'{app}_{mdl}_export_options',
            ),
        ]
        return custom + urls

    # ----------------------------------------------------------------
    # Session helpers
    # ----------------------------------------------------------------

    def _session_key(self) -> str:
        return f'export_pks_{self.model._meta.label_lower}'

    def _redirect_to_options_page(self, request, queryset, fmt: str):
        pks = list(queryset.values_list('pk', flat=True))
        sk = self._session_key()
        request.session[sk] = pks
        request.session[f'{sk}_fmt'] = fmt

        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        url = reverse(f'admin:{app}_{mdl}_export_options') + f'?format={fmt}'
        return redirect(url)

    # ----------------------------------------------------------------
    # Options page view
    # ----------------------------------------------------------------

    def export_options_view(self, request):
        from exports.forms import ExportOptionsForm

        config = self.get_export_config()
        sk = self._session_key()
        pks = request.session.get(sk, [])

        if not pks:
            self.message_user(
                request,
                "Export session expired. Please re-select records and try again.",
                level=messages.ERROR,
            )
            return redirect('../')

        queryset = self.model.objects.filter(pk__in=pks)
        pre_fmt = request.GET.get('format', config.default_format)

        if request.method == 'POST':
            form = ExportOptionsForm(
                request.POST,
                enabled_formats=config.enabled_formats,
                initial_format=pre_fmt,
            )
            if form.is_valid():
                opts = form.cleaned_data
                if opts.get('save_as_preference'):
                    self._save_user_preference(request.user, opts)
                return self._perform_export(request, queryset, opts)
        else:
            initial = self.get_effective_options(request.user)
            initial['format'] = pre_fmt
            form = ExportOptionsForm(
                enabled_formats=config.enabled_formats,
                initial_format=pre_fmt,
                initial=initial,
            )

        context = {
            **self.admin_site.each_context(request),
            'title': f"Export {self.model._meta.verbose_name_plural.title()}",
            'form': form,
            'record_count': queryset.count(),
            'model_name': self.model._meta.verbose_name_plural.title(),
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'config': config,
        }
        return TemplateResponse(request, 'admin/exports/export_options.html', context)

    # ----------------------------------------------------------------
    # Export dispatch
    # ----------------------------------------------------------------

    def _perform_export(self, request, queryset, options: dict):
        from exports.models import ExportLog

        # RBAC: re-verify export permission (guards direct URL access)
        try:
            from rbac.services import PermissionService
            if not PermissionService.has_module_permission(request.user, self.get_module_key(), 'export'):
                self.message_user(request, "You do not have permission to export this data.", level=messages.ERROR)
                return redirect('../')
        except Exception:
            pass  # rbac not available — proceed

        config = self.get_export_config()
        fmt = options.get('format', 'excel')

        # Enforce row limit
        if config.max_rows and queryset.count() > config.max_rows:
            status_flag = 'partial'
            queryset = queryset[:config.max_rows]
        else:
            status_flag = 'success'

        start_ts = time.time()

        try:
            backend = self._get_format_backend(fmt)
            response = backend.export(
                admin_instance=self,
                queryset=queryset,
                options=options,
            )

            # ZIP wrapping
            inner_filename = ''
            if options.get('compress_zip') and fmt != 'zip':
                cd = response.get('Content-Disposition', '')
                inner_filename = cd.split('filename=')[-1].strip('"').strip("'")
                response, zip_filename = backend.wrap_in_zip(response, inner_filename)
                served_filename = zip_filename
            else:
                cd = response.get('Content-Disposition', '')
                served_filename = cd.split('filename=')[-1].strip('"').strip("'")

            duration_ms = int((time.time() - start_ts) * 1000)
            file_size = len(response.content) if hasattr(response, 'content') else None

            ExportLog.objects.create(
                user=request.user,
                module_key=self.get_module_key(),
                model_name=self.model._meta.verbose_name,
                export_format=fmt,
                include_headers=options.get('include_headers', True),
                include_footer=options.get('include_footer', False),
                compressed=options.get('compress_zip', False),
                date_format=options.get('date_format', '%Y-%m-%d'),
                status=status_flag,
                record_count=queryset.count() if not isinstance(queryset, list) else len(queryset),
                file_size_bytes=file_size,
                duration_ms=duration_ms,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                filename=served_filename,
            )

            if status_flag == 'partial':
                self.message_user(
                    request,
                    f"Export limited to {config.max_rows} rows (row limit). "
                    "Adjust the limit in Export Configuration if needed.",
                    level=messages.WARNING,
                )

            return response

        except ImportError as e:
            logger.error("Export backend not available: %s", e)
            self.message_user(request, str(e), level=messages.ERROR)
        except Exception as e:
            logger.exception("Export failed for %s", self.get_module_key())
            duration_ms = int((time.time() - start_ts) * 1000)
            ExportLog.objects.create(
                user=request.user,
                module_key=self.get_module_key(),
                model_name=self.model._meta.verbose_name,
                export_format=fmt,
                status='failed',
                error_message=str(e),
                duration_ms=duration_ms,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
            )
            self.message_user(request, f"Export failed: {e}", level=messages.ERROR)

        return redirect('../')

    def _get_format_backend(self, fmt: str):
        from exports.backends import ExcelExporter, CsvExporter, JsonExporter, PdfExporter, OdsExporter
        BACKENDS = {
            'excel': ExcelExporter,
            'csv': CsvExporter,
            'json': JsonExporter,
            'pdf': PdfExporter,
            'ods': OdsExporter,
        }
        cls = BACKENDS.get(fmt)
        if cls is None:
            raise ValueError(f"Unsupported export format: {fmt!r}")
        return cls()

    def _get_client_ip(self, request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def _save_user_preference(self, user, options: dict):
        from exports.models import UserExportPreference
        UserExportPreference.objects.update_or_create(
            user=user,
            module_key=self.get_module_key(),
            defaults={
                'preferred_format': options.get('format', 'excel'),
                'include_headers': options.get('include_headers', True),
                'include_footer': options.get('include_footer', False),
                'compress_zip': options.get('compress_zip', False),
                'date_format': options.get('date_format', '%Y-%m-%d'),
            },
        )

    # ----------------------------------------------------------------
    # Backwards-compat: keep export_as_excel for anything that calls it directly
    # ----------------------------------------------------------------

    def export_as_excel(self, request, queryset):
        """Legacy entry point — routes through the new system."""
        return self._redirect_to_options_page(request, queryset, 'excel')

    export_as_excel.short_description = "Export selected as EXCEL"
