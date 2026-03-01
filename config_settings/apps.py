"""
config_settings/apps.py
=========================
Registers signals on app startup via ready().
Without this, none of the signals in signals.py will fire.
"""

from django.apps import AppConfig


class ConfigSettingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'config_settings'
    verbose_name = 'ERP Configuration'

    def ready(self):
        """
        Import signals module to register all signal handlers.
        This must be done here — importing at the top of models.py
        causes circular import errors.
        """
        import config_settings.signals  # noqa: F401