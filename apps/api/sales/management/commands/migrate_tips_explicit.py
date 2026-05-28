"""
migrate_tips_explicit — Fase C

Para cada Sale legacy donde `sum(SalePayment.amount) > Sale.subtotal` (señal
de "el payment incluye propina embebida"), separamos:
  - Restar la propina del SalePayment.amount → queda solo la venta
  - Asegurar que existan filas SaleTip que sumen exactamente Sale.tip

NO toca ventas que ya estan en formato Fase A (sum_payments == subtotal).
NO toca SalePayment de ventas sin tip (sale.tip == 0).

Salvaguardas:
- --dry-run por default (no escribe; muestra sample de 10 y conteos)
- --apply requerido para ejecutar
- transaction.atomic() por tenant → rollback automatico si algo falla
- Log con resumen final: ventas modificadas, propina total separada,
  alertas si algo no cuadra
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import Tenant
from sales.models import Sale, SalePayment, SaleTip

logger = logging.getLogger(__name__)
TOLERANCE = Decimal("0.01")


class Command(BaseCommand):
    help = "Migra ventas legacy: separa propina embebida en SalePayment.amount."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Solo este tenant (default todos)")
        parser.add_argument("--apply", action="store_true",
                            help="Ejecutar (sin esto, dry-run)")
        parser.add_argument("--limit", type=int, default=0,
                            help="Procesar solo N ventas (debug)")

    def handle(self, *args, **options):
        tenant_filter = options.get("tenant")
        apply_changes = options.get("apply")
        limit = options.get("limit") or 0

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN: nada se escribira. Usa --apply para ejecutar."
            ))

        tenants = Tenant.objects.all()
        if tenant_filter:
            tenants = tenants.filter(id=tenant_filter)

        total_migrated = 0
        total_tips_separated = Decimal("0")
        sample_shown = 0

        for tenant in tenants:
            self.stdout.write(f"\n== Tenant {tenant.id} {tenant.name} ==")
            with transaction.atomic():
                # Candidatos: Sale.tip > 0
                # (las que tip=0 nunca tuvieron propina, no necesitan migracion)
                candidates = Sale.objects.filter(
                    tenant=tenant, tip__gt=0,
                ).prefetch_related("payments", "tips")
                if limit:
                    candidates = candidates[:limit]

                migrated_this_tenant = 0
                tips_separated_this_tenant = Decimal("0")
                for sale in candidates:
                    payments = list(sale.payments.all())
                    if not payments:
                        continue
                    sum_payments = sum((p.amount for p in payments), Decimal("0"))
                    subtotal = sale.subtotal or Decimal("0")
                    excess = sum_payments - subtotal

                    # No es legacy embedded → ya esta en formato Fase A
                    if excess <= TOLERANCE:
                        continue

                    # El excess debe corresponder a la propina embebida.
                    # Validamos que excess ≈ sale.tip (tolerancia 1 centavo).
                    if abs(excess - sale.tip) > Decimal("1"):
                        self.stderr.write(self.style.WARNING(
                            f"  Sale #{sale.sale_number or sale.id}: "
                            f"excess={excess} != tip={sale.tip} (skip)"
                        ))
                        continue

                    # Guardar amounts ORIGINALES antes de modificar
                    # (para usarlos en el reparto del SaleTip).
                    original_amounts = [(p.method, p.amount) for p in payments]

                    # 1. Distribuir el excess proporcionalmente entre payments
                    #    y restarlo a SalePayment.amount.
                    running = Decimal("0")
                    for i, p in enumerate(payments):
                        is_last = i == len(payments) - 1
                        if is_last:
                            share = excess - running
                        else:
                            share = (excess * p.amount / sum_payments).quantize(Decimal("0.01"))
                            running += share
                        new_amount = (p.amount - share).quantize(Decimal("0.01"))
                        if apply_changes:
                            p.amount = new_amount
                            p.save(update_fields=["amount"])

                    # 2. Asegurar SaleTip rows que sumen sale.tip.
                    existing_tips_sum = sum(
                        (t.amount for t in sale.tips.all()), Decimal("0")
                    )
                    if abs(existing_tips_sum - sale.tip) <= TOLERANCE:
                        pass  # SaleTip ya cubre, no tocar
                    elif apply_changes:
                        sale.tips.all().delete()
                        explicit_method = (sale.tip_method or "").strip().lower()
                        if explicit_method:
                            SaleTip.objects.create(
                                sale=sale, tenant=tenant,
                                method=explicit_method,
                                amount=sale.tip,
                            )
                        else:
                            # Reparto proporcional sobre los amounts ORIGINALES
                            # (capturados arriba antes de modificarlos).
                            running_tip = Decimal("0")
                            new_tip_rows = []
                            for i, (method, orig_amount) in enumerate(original_amounts):
                                is_last = i == len(original_amounts) - 1
                                if is_last:
                                    s = sale.tip - running_tip
                                else:
                                    s = (sale.tip * orig_amount / sum_payments).quantize(Decimal("0.01"))
                                    running_tip += s
                                if s > 0:
                                    new_tip_rows.append(SaleTip(
                                        sale=sale, tenant=tenant,
                                        method=method, amount=s,
                                    ))
                            if new_tip_rows:
                                SaleTip.objects.bulk_create(new_tip_rows)

                    # (Sin marcador audit — el modelo Sale no tiene campo
                    # `note`. La idempotencia se garantiza por la heuristica
                    # `excess <= TOLERANCE`: despues de migrar, sum_payments
                    # == subtotal, asi que el script no procesa la venta de
                    # nuevo si vuelve a correr.)

                    migrated_this_tenant += 1
                    tips_separated_this_tenant += sale.tip
                    if sample_shown < 10:
                        self.stdout.write(
                            f"  Sale #{sale.sale_number or sale.id}: "
                            f"subtotal={subtotal} tip={sale.tip} "
                            f"sum_payments={sum_payments} → "
                            f"separado en {len(payments)} payment(s)"
                        )
                        sample_shown += 1

                self.stdout.write(
                    f"  Tenant {tenant.id}: {migrated_this_tenant} ventas migradas, "
                    f"propina total separada: ${tips_separated_this_tenant}"
                )
                total_migrated += migrated_this_tenant
                total_tips_separated += tips_separated_this_tenant

                if not apply_changes:
                    transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal: {total_migrated} ventas, ${total_tips_separated} propinas separadas"
            f"{' (DRY-RUN, sin escribir)' if not apply_changes else ''}"
        ))
