"""
send_low_stock_alerts
=====================
Ejecuta el envío de alertas por email a los dueños de cada tenant
cuando hay productos con stock por debajo de su mínimo configurado.

Pensado para correr 1 vez al día via cron (típicamente 8:00 AM Chile).

Uso:
    python manage.py send_low_stock_alerts            # todos los tenants
    python manage.py send_low_stock_alerts --tenant 1 # un solo tenant
    python manage.py send_low_stock_alerts --dry-run  # ver qué se enviaría sin enviar
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Envía emails de alerta de stock bajo a los dueños de cada tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None,
                            help="Limita el envío a un tenant específico")
        parser.add_argument("--dry-run", action="store_true", default=False,
                            help="No envía emails, solo lista quiénes recibirían")

    def handle(self, *args, **options):
        # Importamos acá para no costar el startup del management
        from django.conf import settings
        from django.core.mail import send_mail
        from django.db.models import F
        from core.models import Tenant, User, AlertPreference
        from inventory.models import StockItem
        from billing.email_renderers import render_low_stock

        tenant_id = options.get("tenant")
        dry_run = options.get("dry_run", False)

        tenants = Tenant.objects.filter(is_active=True)
        if tenant_id:
            tenants = tenants.filter(id=tenant_id)

        sent = 0
        skipped = 0
        for tenant in tenants:
            owner = User.objects.filter(
                tenant=tenant, role="owner", is_active=True
            ).first()
            if not owner or not owner.email:
                self.stdout.write(f"  [skip] tenant={tenant.id} sin owner con email")
                skipped += 1
                continue

            # Respeta preferencias — si stock_bajo está apagado, saltar.
            try:
                prefs = AlertPreference.objects.get(user=owner)
                if not prefs.stock_bajo:
                    self.stdout.write(f"  [skip] {owner.email} → stock_bajo apagado")
                    skipped += 1
                    continue
            except AlertPreference.DoesNotExist:
                pass

            # Productos bajo el mínimo
            low_items = list(
                StockItem.objects
                .filter(
                    tenant=tenant,
                    product__min_stock__gt=0,
                    product__is_active=True,
                )
                .filter(on_hand__lt=F("product__min_stock"))
                .select_related("product", "warehouse")
                .order_by("on_hand")[:20]
            )
            if not low_items:
                self.stdout.write(f"  [ok] tenant={tenant.id} sin items bajos")
                continue

            critical = [i for i in low_items if i.on_hand <= 0]
            low = [i for i in low_items if i.on_hand > 0]

            subject, plain, html = render_low_stock(
                tenant=tenant, critical_items=critical, low_items=low,
            )

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  [dry] {owner.email} → {len(critical)} críticos, {len(low)} bajos"
                ))
                continue

            try:
                send_mail(
                    subject=subject,
                    message=plain,
                    html_message=html,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                       "Pulstock <noreply@pulstock.cl>"),
                    recipient_list=[owner.email],
                    fail_silently=False,
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [sent] {owner.email} → {len(low_items)} items"
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  [error] {owner.email}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal enviados: {sent} · saltados: {skipped}"
        ))
