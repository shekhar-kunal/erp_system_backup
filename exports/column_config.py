"""
ColumnConfigMixin
=================
Generic mixin that adds per-user, database-persisted column visibility and
ordering to any Django admin changelist view.

Usage
-----
1.  Declare three class-level attributes on your ModelAdmin subclass::

        ALL_LIST_COLUMNS = [
            ('field_name', 'Display Label'),
            ...
        ]
        DEFAULT_COLUMNS  = ['field1', 'field2', ...]   # shown on first visit
        REQUIRED_COLUMNS = ['field1']                  # always visible, cannot be removed

2.  Add ``ColumnConfigMixin`` to the class hierarchy **before**
    ``ConfigurableExportMixin`` (or ``admin.ModelAdmin``)::

        class MyAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin):
            ...

The mixin will:
- Inject a "⚙ Configure Columns" button into the changelist toolbar.
- Serve a drag-and-drop column configuration page at ``configure-columns/``.
- Read/write column preferences from ``UserColumnPreference`` (DB-backed,
  persists across logins).
- Override ``get_list_display()`` and ``get_list_editable()`` at runtime.

If ``ALL_LIST_COLUMNS`` is *not* defined the mixin is a complete no-op.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse


class ColumnConfigMixin:
    """
    Drop-in mixin for per-user, DB-persisted column configuration in Django admin.
    Requires ``ALL_LIST_COLUMNS``, ``DEFAULT_COLUMNS``, ``REQUIRED_COLUMNS``
    to be defined on the concrete admin class.
    """

    # Generic changelist template that adds the "Configure Columns" button.
    # Individual admin classes can still override this with their own template
    # as long as that template also provides the button (or inherits from this one).
    change_list_template = 'admin/column_config/change_list.html'

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _col_model_key(self):
        return f"{self.model._meta.app_label}.{self.model._meta.model_name}"

    def _load_column_pref(self, user):
        """Return the saved column list for *user*, or ``None`` if not set."""
        from exports.models import UserColumnPreference
        try:
            pref = UserColumnPreference.objects.get(
                user=user,
                model_key=self._col_model_key(),
            )
            return pref.columns if pref.columns else None
        except UserColumnPreference.DoesNotExist:
            return None

    def _save_column_pref(self, user, columns):
        from exports.models import UserColumnPreference
        UserColumnPreference.objects.update_or_create(
            user=user,
            model_key=self._col_model_key(),
            defaults={'columns': columns},
        )

    def _reset_column_pref(self, user):
        from exports.models import UserColumnPreference
        UserColumnPreference.objects.filter(
            user=user,
            model_key=self._col_model_key(),
        ).delete()

    # ------------------------------------------------------------------
    # Admin overrides
    # ------------------------------------------------------------------

    def get_list_display(self, request):
        if not hasattr(self, 'ALL_LIST_COLUMNS'):
            return super().get_list_display(request)
        saved = self._load_column_pref(request.user)
        all_fields = {col for col, _ in self.ALL_LIST_COLUMNS}
        if saved:
            filtered = [c for c in saved if c in all_fields]
            if filtered:
                return filtered
        return list(self.DEFAULT_COLUMNS)

    def get_list_editable(self, request):
        if not hasattr(self, 'ALL_LIST_COLUMNS'):
            return super().get_list_editable(request)
        current_display = set(self.get_list_display(request))
        base_editable = super().get_list_editable(request)
        return tuple(f for f in base_editable if f in current_display)

    def get_urls(self):
        urls = super().get_urls()
        if not hasattr(self, 'ALL_LIST_COLUMNS'):
            return urls
        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        custom = [
            path(
                'configure-columns/',
                self.admin_site.admin_view(self.configure_columns_view),
                name=f'{app}_{mdl}_configure_columns',
            ),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        if hasattr(self, 'ALL_LIST_COLUMNS'):
            extra_context = extra_context or {}
            app = self.model._meta.app_label
            mdl = self.model._meta.model_name
            extra_context['configure_columns_url'] = reverse(
                f'admin:{app}_{mdl}_configure_columns'
            )
        return super().changelist_view(request, extra_context=extra_context)

    # ------------------------------------------------------------------
    # Configure columns view
    # ------------------------------------------------------------------

    def configure_columns_view(self, request):
        all_field_names = [col for col, _ in self.ALL_LIST_COLUMNS]
        all_fields_set = set(all_field_names)
        col_labels = dict(self.ALL_LIST_COLUMNS)
        required_set = set(getattr(self, 'REQUIRED_COLUMNS', []))
        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        changelist_url = reverse(f'admin:{app}_{mdl}_changelist')

        if request.GET.get('reset'):
            self._reset_column_pref(request.user)
            messages.success(request, "Column configuration reset to default.")
            return redirect(changelist_url)

        if request.method == 'POST':
            order_str = request.POST.get('col_order', '')
            order = [c for c in order_str.split(',') if c in all_fields_set]
            # Append any field not captured in the drag order
            for col in all_field_names:
                if col not in order:
                    order.append(col)
            selected = set(request.POST.getlist('columns'))
            # Required columns are always included
            selected |= required_set
            visible = [c for c in order if c in selected]
            if not visible:
                visible = list(self.DEFAULT_COLUMNS)
            self._save_column_pref(request.user, visible)
            messages.success(request, "Column configuration saved.")
            return redirect(changelist_url)

        # GET: build context
        current_visible = self._load_column_pref(request.user) or list(self.DEFAULT_COLUMNS)
        visible_set = set(current_visible)
        # Show currently-visible columns first (in saved order), then hidden ones
        ordered = list(current_visible) + [c for c in all_field_names if c not in visible_set]
        columns_config = [
            {
                'field': col,
                'label': col_labels.get(col, col),
                'visible': col in visible_set,
                'required': col in required_set,
            }
            for col in ordered
        ]
        context = {
            **self.admin_site.each_context(request),
            'title': f'Configure Columns \u2013 {self.model._meta.verbose_name_plural.title()}',
            'columns_config': columns_config,
            'changelist_url': changelist_url,
            'opts': self.model._meta,
            'has_view_permission': True,
        }
        return TemplateResponse(
            request,
            'admin/column_config/configure_columns.html',
            context,
        )
