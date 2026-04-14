from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"

    def ready(self):
        # Connect post_save signal for auto-creating trial subscription on new Tenant
        from . import signal  # noqa: F401
