from django.apps import AppConfig


class CajaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'caja'

    def ready(self):
        # Registrar signals (auto-seed de categorías default al crear Tenant)
        from . import signals  # noqa: F401
