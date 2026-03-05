from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'accounts'
    verbose_name       = 'User Accounts'

    def ready(self):
        from accounts.admin import erp_admin_site
        import django.contrib.admin as dj_admin

        # At this point autodiscover() has already run and all @admin.register()
        # decorators have registered models on dj_admin.site (the old default site).
        # We absorb that registry into erp_admin_site and update back-references.
        erp_admin_site._registry.update(dj_admin.site._registry)
        for model_admin in erp_admin_site._registry.values():
            model_admin.admin_site = erp_admin_site

        # Swap so any future admin.site.register() calls also land on erp_admin_site.
        dj_admin.site = erp_admin_site
