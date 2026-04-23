"""
Envía las 8 plantillas de billing a un email de prueba con datos mock.

Uso:
    python manage.py send_billing_previews tu@email.com

Requiere que EMAIL_BACKEND apunte a SMTP real (Brevo/Gmail/etc.) — con
DEBUG=1 el backend es console y no sale del servidor.

Útil para:
- Validar que Outlook / Gmail / Apple Mail renderean el nuevo layout v3.
- Revisar copy y estética sin tener que disparar flujos reales de billing.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import tasks as T


class _MockPlan:
    name = "Plan Pro"
    price_clp = 29990


class _MockTenant:
    name = "Café Don Pedro"


class _MockUser:
    email = "demo@pulstock.cl"
    username = "don.pedro"
    first_name = "Pedro"
    pk = 1


class _MockSub:
    def __init__(self):
        self.plan = _MockPlan()
        self.tenant = _MockTenant()
        self.current_period_end = timezone.now() + timedelta(days=30)
        self.payment_retry_count = 2


class Command(BaseCommand):
    help = "Envía las 8 plantillas de billing (con datos mock) al email indicado."

    def add_arguments(self, parser):
        parser.add_argument("to", type=str, help="Email destinatario (ej: tu@gmail.com)")
        parser.add_argument(
            "--only",
            type=str,
            default=None,
            help="Enviar solo N: welcome,trial_reminder,renewal,payment_failed,"
                 "suspension,payment_recovered,trial_converted,trial_expired",
        )

    def handle(self, *args, **options):
        to = options["to"].strip()
        only = (options["only"] or "").strip().lower()

        backend = getattr(settings, "EMAIL_BACKEND", "")
        self.stdout.write(self.style.WARNING(f"EMAIL_BACKEND = {backend}"))
        if "console" in backend:
            self.stdout.write(self.style.WARNING(
                "[!] Backend es 'console' — los emails NO van a salir del servidor.\n"
                "    Configurá SMTP (Brevo/Gmail) en .env o ejecuta con DEBUG=0 + vars de prod."
            ))

        # Monkey-patch: forzar destinatario + prefijo [PREVIEW].
        # (Welcome usa user.email directo, trial/renewal usan _get_owner_email;
        # lo más seguro es interceptar el envío final.)
        T._get_owner_email = lambda sub: to

        sub = _MockSub()
        user = _MockUser()
        user.email = to  # también por seguridad para welcome
        tenant = _MockTenant()
        plan = _MockPlan()

        orig_safe = T._send_email_safe
        def patched(to_, subject, body, html_message=None):
            return orig_safe(to, f"[PREVIEW] {subject}", body, html_message)
        T._send_email_safe = patched

        previews = [
            ("welcome", lambda: T._send_welcome_email(user, tenant, plan)),
            ("trial_reminder", lambda: T._send_trial_reminder(sub, 3)),
            ("renewal", lambda: T._send_renewal_reminder(sub, 5)),
            ("payment_failed", lambda: T._send_payment_failed_notice(sub)),
            ("suspension", lambda: T._send_suspension_notice(sub)),
            ("payment_recovered", lambda: T._send_payment_recovered_notice(sub)),
            ("trial_converted", lambda: T._send_trial_converted_notice(sub)),
            ("trial_expired", lambda: T._send_trial_expired_notice(sub)),
        ]

        if only:
            wanted = {k.strip() for k in only.split(",") if k.strip()}
            previews = [(n, f) for (n, f) in previews if n in wanted]
            if not previews:
                self.stderr.write(self.style.ERROR(f"--only '{only}' no matchea ningún preview"))
                return

        sent, failed = 0, 0
        for name, fn in previews:
            try:
                fn()
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"[OK] {name:<22} enviado a {to}"))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"[ERR] {name:<22} FALLO: {e}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Listo: {sent} enviados, {failed} con error"))
        if sent > 0 and "console" not in backend:
            self.stdout.write(
                "-> Revisa el inbox de " + to + " (mirá también spam). "
                "Los asuntos empiezan con [PREVIEW]."
            )
