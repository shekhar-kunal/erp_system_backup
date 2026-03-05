"""
ERPAdminMixin — add as the LEFTMOST base class to any ModelAdmin.

MRO pattern:
    class MyAdmin(ERPAdminMixin, ColumnConfigMixin, ConfigurableExportMixin, admin.ModelAdmin): ...
    class CategoryAdmin(ERPAdminMixin, ColumnConfigMixin, DraggableMPTTAdmin): ...

View-only mode
--------------
By default, opening any existing record (GET) shows a fully read-only form:
  - All fields are plain text — no inputs
  - No Save / Save and continue / Save and add another buttons
  - Title reads "View <model>" instead of "Change <model>"
  - An "✎ Edit" button appears in the toolbar for users who have edit permission

To enter edit mode, click the "Edit" button (navigates to ?edit=1).

Reassign-before-delete
----------------------
For any model that has PROTECT FK relationships pointing to it, a
"Reassign all references, then delete" action is added automatically.
The intermediate page:
  1. Lists the records to delete and every model/field that references them
  2. Offers a replacement-record dropdown (same model type)
  3. Bulk-updates all PROTECT FK fields, then deletes the original records

Permission model
----------------
RBAC is the SOLE authority for non-superusers.  super() is NOT called for
permission checks so Django's native permission tables have no effect.
"""
from django.contrib import messages
from django.db.models import PROTECT
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .services import PermissionService


class ERPAdminMixin:

    # Use a custom change-form template that adds the "Edit" button.
    change_form_template = 'admin/erp/change_form.html'

    def _rbac_module_key(self):
        return f'{self.model._meta.app_label}.{self.model._meta.model_name}'

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _can_edit_rbac(self, request):
        if request.user.is_superuser:
            return True
        return PermissionService.has_module_permission(
            request.user, self._rbac_module_key(), 'edit'
        )

    def _get_protect_relations(self):
        """Return all PROTECT FK relations pointing at this model."""
        return [
            rel for rel in self.model._meta.related_objects
            if rel.on_delete is PROTECT
        ]

    # ------------------------------------------------------------------ #
    # Permission gates — RBAC is the sole authority for non-superusers    #
    # ------------------------------------------------------------------ #

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return (
            PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'view')
            or PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'edit')
        )

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'create')

    def has_change_permission(self, request, obj=None):
        if getattr(request, '_erp_view_only', False):
            return False
        return self._can_edit_rbac(request)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'delete')

    # ------------------------------------------------------------------ #
    # View-only mode                                                       #
    # ------------------------------------------------------------------ #

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}

        is_popup = '_popup' in request.GET
        view_only = (
            request.method == 'GET'
            and 'edit' not in request.GET
            and not is_popup
        )

        if view_only:
            request._erp_view_only = True
            extra_context['erp_view_only'] = True
            if self._can_edit_rbac(request):
                extra_context['erp_edit_url'] = '?edit=1'

        try:
            return super().change_view(request, object_id, form_url, extra_context)
        finally:
            request._erp_view_only = False

    # ------------------------------------------------------------------ #
    # Field-level security                                                 #
    # ------------------------------------------------------------------ #

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            all_fields = [f.name for f in self.model._meta.fields]
            rbac_ro = PermissionService.get_readonly_fields_for_user(
                request.user, self._rbac_module_key(), all_fields,
            )
            readonly = list(set(readonly + rbac_ro))
        return readonly

    # ------------------------------------------------------------------ #
    # Reassign-before-delete — generic, auto-enabled for PROTECT models   #
    # ------------------------------------------------------------------ #

    def get_urls(self):
        urls = super().get_urls()
        # Only register the reassign-delete URL if this model has PROTECT FKs
        if self._get_protect_relations():
            app = self.model._meta.app_label
            mdl = self.model._meta.model_name
            custom = [
                path(
                    'reassign-delete/',
                    self.admin_site.admin_view(self.reassign_delete_view),
                    name=f'{app}_{mdl}_reassign_delete',
                ),
            ]
            return custom + urls
        return urls

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self._get_protect_relations():
            # Replace the standard "Delete selected" with the reassign action so
            # users never hit a raw ProtectedError from the changelist.
            actions.pop('delete_selected', None)
            if 'reassign_and_delete' not in actions:
                desc = (
                    f"Reassign all references, then delete selected "
                    f"{self.model._meta.verbose_name_plural}"
                )
                actions['reassign_and_delete'] = (
                    self._generic_reassign_action,
                    'reassign_and_delete',
                    desc,
                )
        return actions

    def _generic_reassign_action(self, modeladmin, request, queryset):
        ids = ','.join(str(pk) for pk in queryset.values_list('pk', flat=True))
        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        url = reverse(f'admin:{app}_{mdl}_reassign_delete') + f'?ids={ids}'
        return redirect(url)

    def reassign_delete_view(self, request):
        """
        Intermediate page: reassign PROTECT FK references to a chosen
        replacement, then delete the original records.
        """
        from django.db import transaction

        app = self.model._meta.app_label
        mdl = self.model._meta.model_name
        changelist_url = reverse(f'admin:{app}_{mdl}_changelist')
        verbose = self.model._meta.verbose_name
        verbose_plural = self.model._meta.verbose_name_plural

        # Parse IDs from GET (initial) or POST (hidden field after submission)
        raw_ids = request.GET.get('ids') or request.POST.get('object_ids', '')
        try:
            obj_ids = [int(i) for i in raw_ids.split(',') if i.strip()]
        except ValueError:
            self.message_user(request, "Invalid record IDs.", level=messages.ERROR)
            return redirect(changelist_url)

        objects_to_delete = self.model.objects.filter(pk__in=obj_ids)
        if not objects_to_delete.exists():
            self.message_user(request, "No matching records found.", level=messages.ERROR)
            return redirect(changelist_url)

        protect_relations = self._get_protect_relations()
        available_replacements = self.model.objects.exclude(pk__in=obj_ids)
        error = None

        # Build a human-readable summary of what will be affected
        relation_summary = []
        for rel in protect_relations:
            related_model = rel.related_model
            field_name = rel.field.name
            count = related_model.objects.filter(
                **{f'{field_name}__in': obj_ids}
            ).count()
            if count:
                relation_summary.append({
                    'model_name': related_model._meta.verbose_name_plural.title(),
                    'field_name': field_name,
                    'count': count,
                })

        if request.method == 'POST':
            replacement_id = request.POST.get('replacement', '').strip()
            needs_replacement = bool(relation_summary)  # True when there are refs to reassign

            if needs_replacement and not available_replacements.exists():
                error = (
                    f"No replacement {verbose} is available. "
                    f"Create a new {verbose} first, then retry."
                )
            elif needs_replacement and not replacement_id:
                error = f"Please select a replacement {verbose} before continuing."
            elif needs_replacement:
                try:
                    replacement = self.model.objects.get(pk=replacement_id)
                except self.model.DoesNotExist:
                    error = "The selected replacement record no longer exists."

            if not error:
                try:
                    with transaction.atomic():
                        if needs_replacement:
                            for rel in protect_relations:
                                related_model = rel.related_model
                                field_name = rel.field.name
                                related_model.objects.filter(
                                    **{f'{field_name}__in': obj_ids}
                                ).update(**{field_name: replacement})

                        deleted_names = [str(obj) for obj in objects_to_delete]
                        count = objects_to_delete.count()
                        objects_to_delete.delete()

                    if needs_replacement:
                        msg = (
                            f"Reassigned all references to \"{replacement}\" and deleted "
                            f"{count} {verbose if count == 1 else verbose_plural}: "
                            f"{', '.join(deleted_names)}."
                        )
                    else:
                        msg = (
                            f"Deleted {count} {verbose if count == 1 else verbose_plural}: "
                            f"{', '.join(deleted_names)}."
                        )
                    self.message_user(request, msg, level=messages.SUCCESS)
                    return redirect(changelist_url)
                except Exception as exc:
                    error = f"Deletion failed: {exc}"

        context = {
            **self.admin_site.each_context(request),
            'title': f'Reassign & delete {verbose_plural}',
            'objects_to_delete': objects_to_delete,
            'object_ids': raw_ids,
            'available_replacements': available_replacements,
            'relation_summary': relation_summary,
            'verbose_name': verbose,
            'verbose_name_plural': verbose_plural,
            'changelist_url': changelist_url,
            'opts': self.model._meta,
            'error': error,
        }
        return TemplateResponse(request, 'admin/erp/reassign_delete.html', context)

    # ------------------------------------------------------------------ #
    # Audit logging                                                        #
    # ------------------------------------------------------------------ #

    def _capture_old_values(self, obj):
        try:
            old = self.model.objects.get(pk=obj.pk)
            return {f.name: str(getattr(old, f.name, '')) for f in self.model._meta.fields}
        except self.model.DoesNotExist:
            return None

    def _capture_new_values(self, obj):
        return {f.name: str(getattr(obj, f.name, '')) for f in self.model._meta.fields}

    def save_model(self, request, obj, form, change):
        old_vals = self._capture_old_values(obj) if change else None
        super().save_model(request, obj, form, change)
        PermissionService.log_action(
            user=request.user,
            action='update' if change else 'create',
            module=self._rbac_module_key(),
            model_name=self.model.__name__,
            object_id=obj.pk,
            object_repr=str(obj),
            old_values=old_vals,
            new_values=self._capture_new_values(obj),
            ip_address=PermissionService.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

    def delete_model(self, request, obj):
        old_vals = self._capture_new_values(obj)
        PermissionService.log_action(
            user=request.user,
            action='delete',
            module=self._rbac_module_key(),
            model_name=self.model.__name__,
            object_id=obj.pk,
            object_repr=str(obj),
            old_values=old_vals,
            ip_address=PermissionService.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)
