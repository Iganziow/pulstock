"""
Envía las 10 plantillas de email (8 billing + 2 operacionales) a un email
de prueba con datos mock.

Uso:
    python manage.py send_billing_previews tu@email.com

Requiere que EMAIL_BACKEND apunte a SMTP real (Brevo/Gmail/etc.) — con
DEBUG=1 el backend es console y no sale del servidor.

Útil para:
- Validar que Outlook / Gmail / Apple Mail renderean el nuevo layout
- Revisar copy y estética sin disparar flujos reales de billing
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import tasks as T
from billing import email_renderers as R


class _MockPlan:
    name = "Plan Pro"
    price_clp = 29990


class _MockTenant:
    id = 1
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
        self.pk = 42
        self.current_period_end = timezone.now() + timedelta(days=30)
        self.trial_ends_at = timezone.now() + timedelta(days=3)
        self.payment_retry_count = 2
        self.next_retry_at = timezone.now() + timedelta(days=2)
        self.suspended_at = timezone.now() - timedelta(hours=6)


class _MockProduct:
    def __init__(self, name, sku, min_stock):
        self.name = name
        self.sku = sku
        self.min_stock = min_stock


class _MockWarehouse:
    def __init__(self, name):
        self.name = name


class _MockStockItem:
    def __init__(self, product_name, sku, warehouse_name, on_hand, min_stock):
        self.product = _MockProduct(product_name, sku, min_stock)
        self.warehouse = _MockWarehouse(warehouse_name)
        self.on_hand = Decimal(str(on_hand))


def _mock_abc_items():
    """Datos ABC de ejemplo (items A con revenue alto, B medio, C bajo)."""
    a = [
        {"product_name": "Café Espresso 250g",  "sku": "CAF-250",  "units": 412, "revenue": 4120000, "profit": 1648000, "margin_pct": 40, "abc_class": "A"},
        {"product_name": "Café en grano 1kg",   "sku": "CAF-1KG",  "units": 180, "revenue": 3240000, "profit": 1296000, "margin_pct": 40, "abc_class": "A"},
        {"product_name": "Capsulas Nespresso", "sku": "CAP-NES",  "units": 640, "revenue": 2240000, "profit":  784000, "margin_pct": 35, "abc_class": "A"},
        {"product_name": "Filtros V60 x100",    "sku": "FIL-V60",  "units": 220, "revenue": 1320000, "profit":  528000, "margin_pct": 40, "abc_class": "A"},
        {"product_name": "Molinillo manual",    "sku": "MOL-MAN",  "units":  38, "revenue":  950000, "profit":  285000, "margin_pct": 30, "abc_class": "A"},
    ]
    b = [
        {"product_name": "Tazas cerámica 250ml","sku": "TAZ-250",  "units": 145, "revenue":  435000, "profit":  130000, "margin_pct": 30, "abc_class": "B"},
        {"product_name": "Leche condensada",    "sku": "LEC-CON",  "units":  92, "revenue":  276000, "profit":   82000, "margin_pct": 30, "abc_class": "B"},
        {"product_name": "Jarabe vainilla",     "sku": "JAR-VAN",  "units":  55, "revenue":  220000, "profit":   88000, "margin_pct": 40, "abc_class": "B"},
    ]
    c = [
        {"product_name": "Servilletas pack",    "sku": "SER-PCK",  "units": 210, "revenue":   84000, "profit":   21000, "margin_pct": 25, "abc_class": "C"},
        {"product_name": "Removedor palitos",   "sku": "REM-PAL",  "units": 410, "revenue":   41000, "profit":    8000, "margin_pct": 20, "abc_class": "C"},
    ]
    return a, b, c


def _mock_low_stock_items():
    """Lista de stock items mock (algunos agotados, otros bajos)."""
    critical = [
        _MockStockItem("Café Espresso 250g",  "CAF-250",  "Bodega Central",   0,  20),
        _MockStockItem("Leche condensada",    "LEC-CON",  "Local Providencia", 0,  10),
    ]
    low = [
        _MockStockItem("Capsulas Nespresso", "CAP-NES",  "Bodega Central",   5,  15),
        _MockStockItem("Filtros V60 x100",   "FIL-V60",  "Bodega Central",   3,  10),
        _MockStockItem("Tazas cerámica 250ml","TAZ-250", "Local Centro",     4,  12),
    ]
    return critical, low


class Command(BaseCommand):
    help = "Envía las 10 plantillas de email (8 billing + ABC + low_stock) con mocks."

    def add_arguments(self, parser):
        parser.add_argument("to", type=str, help="Email destinatario")
        parser.add_argument(
            "--only",
            type=str,
            default=None,
            help="Enviar solo N: welcome,trial_reminder,renewal,payment_failed,"
                 "suspension,payment_recovered,trial_converted,trial_expired,"
                 "abc_weekly,low_stock",
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

        # Monkey-patch: forzar destinatario + prefijo [PREVIEW] en subject
        T._get_owner_email = lambda sub: to
        orig_safe = T._send_email_safe
        def patched(to_, subject, body, html_message=None):
            return orig_safe(to, f"[PREVIEW] {subject}", body, html_message)
        T._send_email_safe = patched

        sub = _MockSub()
        user = _MockUser()
        user.email = to
        tenant = _MockTenant()
        plan = _MockPlan()

        a, b, c = _mock_abc_items()
        crit_items, low_items = _mock_low_stock_items()
        total_rev = sum(i["revenue"] for i in a + b + c)
        total_prof = sum(i["profit"] for i in a + b + c)
        date_to = timezone.now().date()
        date_from = date_to - timedelta(days=90)

        from django.core.mail import send_mail
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "Pulstock <noreply@pulstock.cl>")

        def _send_raw(subject, plain, html):
            """Para los renderers que no pasan por tasks._send_email_safe (ABC / low_stock)."""
            send_mail(
                f"[PREVIEW] {subject}", plain,
                from_email, [to], fail_silently=False,
                html_message=html,
            )

        previews = [
            ("welcome",           lambda: T._send_welcome_email(user, tenant, plan)),
            ("trial_reminder",    lambda: T._send_trial_reminder(sub, 3)),
            ("renewal",           lambda: T._send_renewal_reminder(sub, 5)),
            ("payment_failed",    lambda: T._send_payment_failed_notice(sub)),
            ("suspension",        lambda: T._send_suspension_notice(sub)),
            ("payment_recovered", lambda: T._send_payment_recovered_notice(sub)),
            ("trial_converted",   lambda: T._send_trial_converted_notice(sub)),
            ("trial_expired",     lambda: T._send_trial_expired_notice(sub)),
            ("abc_weekly",        lambda: _send_raw(*R.render_abc_weekly(
                                        tenant, date_from, date_to, a, b, c,
                                        total_rev, total_prof))),
            ("low_stock",         lambda: _send_raw(*R.render_low_stock(
                                        tenant, crit_items, low_items))),
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
