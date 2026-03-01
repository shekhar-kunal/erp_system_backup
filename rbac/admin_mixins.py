"""
ERPAdminMixin — add as the LEFTMOST base class to any ModelAdmin.

MRO pattern:
    class MyAdmin(ERPAdminMixin, ConfigurableExportMixin, admin.ModelAdmin): ...
    class CategoryAdmin(ERPAdminMixin, DraggableMPTTAdmin): ...

Rules:
- Always call super() AFTER the RBAC gate so existing False-returns are preserved.
- Superusers bypass all RBAC checks.
- All creates/updates/deletes are audit-logged automatically.
"""
from .services import PermissionService


class ERPAdminMixin:

    def _rbac_module_key(self):
        return f'{self.model._meta.app_label}.{self.model._meta.model_name}'

    # ------------------------------------------------------------------ #
    # Permission gates                                                     #
    # ------------------------------------------------------------------ #

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_view_permission(request, obj)
        if not PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'view'):
            return False
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return super().has_add_permission(request)
        if not PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'create'):
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_change_permission(request, obj)
        if not PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'edit'):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_delete_permission(request, obj)
        if not PermissionService.has_module_permission(request.user, self._rbac_module_key(), 'delete'):
            return False
        return super().has_delete_permission(request, obj)

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
    # Audit logging                                                        #
    # ------------------------------------------------------------------ #

    def _capture_old_values(self, obj):
        """Safely fetch old field values before save."""
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
        """Log each deletion individually for a full audit trail."""
        for obj in queryset:
            self.delete_model(request, obj)
