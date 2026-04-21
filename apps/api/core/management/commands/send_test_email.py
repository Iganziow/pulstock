"""
Management command para probar que SMTP está configurado correctamente.

Uso:
    python manage.py send_test_email tu@email.com

Manda un email de prueba al destinatario usando la config SMTP actual.
Útil para validar Brevo/Gmail/Mailgun tras setear las vars de entorno.
"""
import time

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envía un email de prueba usando la config SMTP actual"

    def add_arguments(self, parser):
        parser.add_argument("to", type=str, help="Email destinatario")
        parser.add_argument("--subject", type=str,
                            default="[Pulstock] Test email — SMTP OK")
        parser.add_argument("--from", dest="from_email", type=str,
                            default=None, help="Sobreescribir DEFAULT_FROM_EMAIL")

    def handle(self, *args, **options):
        to = options["to"].strip()
        subject = options["subject"]
        from_email = options["from_email"] or settings.DEFAULT_FROM_EMAIL

        body = (
            "Este es un email de prueba enviado desde Pulstock.\n\n"
            f"Backend   : {settings.EMAIL_BACKEND}\n"
            f"Host      : {getattr(settings, 'EMAIL_HOST', '-')}\n"
            f"Port      : {getattr(settings, 'EMAIL_PORT', '-')}\n"
            f"TLS       : {getattr(settings, 'EMAIL_USE_TLS', False)}\n"
            f"From      : {from_email}\n"
            f"Time      : {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "Si recibís este correo, la configuración SMTP está OK.\n"
        )

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
          <h2 style="color:#4F46E5;">✅ SMTP OK</h2>
          <p>Email de prueba enviado desde <strong>Pulstock</strong>.</p>
          <table style="border-collapse:collapse;width:100%;font-size:13px;">
            <tr><td style="padding:6px;color:#666;">Backend</td>
                <td style="padding:6px;font-family:monospace;">{settings.EMAIL_BACKEND}</td></tr>
            <tr><td style="padding:6px;color:#666;">Host</td>
                <td style="padding:6px;font-family:monospace;">{getattr(settings, 'EMAIL_HOST', '-')}</td></tr>
            <tr><td style="padding:6px;color:#666;">From</td>
                <td style="padding:6px;font-family:monospace;">{from_email}</td></tr>
            <tr><td style="padding:6px;color:#666;">Time</td>
                <td style="padding:6px;font-family:monospace;">{time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
          </table>
          <p style="margin-top:20px;color:#666;font-size:12px;">
            Si recibís este correo, la configuración SMTP está funcionando.
          </p>
        </div>
        """

        self.stdout.write(f"Enviando test a {to} desde {from_email}...")
        try:
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[to],
                html_message=html,
                fail_silently=False,
            )
        except Exception as e:
            raise CommandError(f"Error enviando email: {e}") from e

        if sent:
            self.stdout.write(self.style.SUCCESS(
                f"✓ Email enviado ({sent} destinatario(s)). Revisá tu inbox "
                f"(y spam por las dudas)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Send retornó 0 — el backend no reportó error pero tampoco "
                "envió. Revisá config."
            ))
