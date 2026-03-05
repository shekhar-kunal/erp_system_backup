"""
Centralized permission service for the ERP RBAC system.
All permission checks must go through this service — no hardcoded module logic.
"""
from django.core.cache import cache

CACHE_TTL = 300  # 5 minutes


class PermissionService:

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def is_system_admin(cls, user) -> bool:
        """True if user has full system admin access (bypasses all RBAC checks)."""
        return bool(user and getattr(user, 'is_system_admin', False))

    @staticmethod
    def _get_profile(user):
        """Return UserProfile for user, with 5-min caching."""
        if not user or not user.is_authenticated:
            return None
        key = f'rbac_profile_{user.pk}'
        profile = cache.get(key)
        if profile is None:
            try:
                from .models import UserProfile
                profile = UserProfile.objects.select_related('role', 'department', 'branch').get(user=user)
            except Exception:
                profile = False  # sentinel so we don't re-query
            cache.set(key, profile, CACHE_TTL)
        return profile if profile is not False else None

    @staticmethod
    def _get_module_perm(role_id, module_key):
        """Return ModulePermission for role+module, with 5-min caching."""
        key = f'rbac_mperm_{role_id}_{module_key}'
        perm = cache.get(key)
        if perm is None:
            try:
                from .models import ModulePermission
                perm = ModulePermission.objects.get(role_id=role_id, module=module_key)
            except Exception:
                perm = False
            cache.set(key, perm, CACHE_TTL)
        return perm if perm is not False else None

    @classmethod
    def invalidate_user_cache(cls, user_id):
        """Call after changing a user's profile or role."""
        cache.delete(f'rbac_profile_{user_id}')

    @classmethod
    def invalidate_role_cache(cls, role_id, module_key=None):
        """Call after changing role permissions."""
        if module_key:
            cache.delete(f'rbac_mperm_{role_id}_{module_key}')
        else:
            # Invalidate all module perms for this role
            from .models import MODULE_CHOICES
            for mk, _ in MODULE_CHOICES:
                cache.delete(f'rbac_mperm_{role_id}_{mk}')

    # ------------------------------------------------------------------ #
    # Permission checks                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def has_module_permission(cls, user, module_key, action) -> bool:
        """
        Check if user can perform action on module.
        action: 'view', 'create', 'edit', 'delete', 'approve', 'export', 'print'
        Superusers always return True.
        """
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not user.is_active:
            return False

        profile = cls._get_profile(user)
        if not profile or not profile.role_id or not profile.role.is_active:
            return False

        perm = cls._get_module_perm(profile.role_id, module_key)
        if not perm:
            return False
        return bool(getattr(perm, f'can_{action}', False))

    @classmethod
    def get_all_permissions(cls, user, module_key) -> dict:
        """Return dict of all 7 action flags for this user+module."""
        actions = ['view', 'create', 'edit', 'delete', 'approve', 'export', 'print']
        if user.is_superuser:
            return {a: True for a in actions}
        return {a: cls.has_module_permission(user, module_key, a) for a in actions}

    @classmethod
    def can_access_warehouse(cls, user, warehouse_id) -> bool:
        """
        Returns True if user can access the given warehouse.
        If no warehouses are assigned, all warehouses are accessible (no restriction).
        """
        if user.is_superuser:
            return True
        profile = cls._get_profile(user)
        if not profile:
            return False
        assigned = list(profile.warehouses.values_list('id', flat=True))
        if not assigned:
            return True  # no restriction when no warehouses assigned
        return warehouse_id in assigned

    @classmethod
    def can_access_branch(cls, user, branch_id) -> bool:
        """
        Returns True if user can access the given branch.
        If no branch is assigned, all branches are accessible.
        """
        if user.is_superuser:
            return True
        profile = cls._get_profile(user)
        if not profile or not profile.branch_id:
            return True
        return profile.branch_id == branch_id

    @classmethod
    def is_account_locked(cls, user) -> bool:
        if user.is_superuser:
            return False
        profile = cls._get_profile(user)
        return profile.is_locked() if profile else False

    @classmethod
    def is_within_working_hours(cls, user) -> bool:
        if user.is_superuser:
            return True
        profile = cls._get_profile(user)
        return profile.is_within_working_hours() if profile else True

    # ------------------------------------------------------------------ #
    # Field-level security                                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_visible_fields(cls, user, module_key, all_fields) -> list:
        """Return subset of all_fields that this user can see."""
        if user.is_superuser:
            return list(all_fields)
        profile = cls._get_profile(user)
        if not profile or not profile.role_id:
            return list(all_fields)
        from .models import FieldPermission
        hidden = set(FieldPermission.objects.filter(
            role_id=profile.role_id, module=module_key, can_view=False,
        ).values_list('field_name', flat=True))
        return [f for f in all_fields if f not in hidden]

    @classmethod
    def get_readonly_fields_for_user(cls, user, module_key, all_fields) -> list:
        """Return fields that the user can see but not edit."""
        if user.is_superuser:
            return []
        profile = cls._get_profile(user)
        if not profile or not profile.role_id:
            return []
        from .models import FieldPermission
        readonly = set(FieldPermission.objects.filter(
            role_id=profile.role_id, module=module_key, can_view=True, can_edit=False,
        ).values_list('field_name', flat=True))
        return [f for f in all_fields if f in readonly]

    # ------------------------------------------------------------------ #
    # Export format control                                                #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_allowed_export_formats(cls, user, module_key):
        """
        Returns allowed export formats for user+module.
        None = all (superuser or no restriction).
        [] = no export allowed.
        ['excel', 'csv'] = specific formats allowed.
        """
        if user.is_superuser:
            return None  # all formats
        if not cls.has_module_permission(user, module_key, 'export'):
            return []
        profile = cls._get_profile(user)
        if not profile or not profile.role_id:
            return []
        perm = cls._get_module_perm(profile.role_id, module_key)
        if not perm:
            return []
        role_formats = perm.allowed_export_formats or []
        return role_formats if role_formats else None  # empty list = all allowed

    # ------------------------------------------------------------------ #
    # Approval workflow                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def check_approval_requirement(cls, user, module_key, action, amount=None):
        """
        Returns (needs_approval, required_level, rule).
        needs_approval: bool — whether approval is needed
        required_level: int — minimum approval_level required
        rule: ApprovalRule instance or None
        If user has sufficient approval_level, returns (False, 0, None).
        """
        from .models import ApprovalRule
        rules = ApprovalRule.objects.filter(
            module=module_key, action=action, is_active=True,
        ).order_by('sequence')

        profile = cls._get_profile(user)
        user_level = profile.approval_level if profile else 0

        for rule in rules:
            if rule.min_amount is not None and amount is not None and amount < rule.min_amount:
                continue
            if user_level < rule.required_approval_level:
                return True, rule.required_approval_level, rule
            if rule.required_role and (not profile or not profile.role or profile.role != rule.required_role):
                return True, rule.required_approval_level, rule

        return False, 0, None

    # ------------------------------------------------------------------ #
    # Audit logging                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def log_action(
        user, action, module='', model_name='', object_id='',
        object_repr='', old_values=None, new_values=None,
        ip_address=None, user_agent='', extra=None,
    ):
        """Create an AuditLog record. Safe to call even if rbac tables are not yet migrated."""
        try:
            from .models import AuditLog
            AuditLog.objects.create(
                user=user,
                action=action,
                module=module,
                model_name=model_name,
                object_id=str(object_id) if object_id else '',
                object_repr=str(object_repr)[:200],
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=(user_agent or '')[:255],
                extra=extra,
            )
        except Exception:
            pass  # Never crash the main request for audit logging

    @staticmethod
    def get_client_ip(request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
