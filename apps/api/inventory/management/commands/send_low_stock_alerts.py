"""
send_low_stock_alerts
=====================
Envía email diario al dueño de cada tenant con productos que necesitan
reposición. Usa una lógica HÍBRIDA con 3 condiciones (la primera que se
cumpla dispara la alerta para ese producto):

  1. Stock ≤ min_stock CONFIGURADO MANUALMENTE por el dueño en Catálogo
     → "Bajo el mínimo que tú definiste"
  2. Stock ≤ min_stock_auto (= avg_daily_ventas_14d × 2)
     → "Te alcanza para menos de 2 días" (umbral personalizado por
        producto basado en su rotación REAL)
  3. Forecast predice agotamiento en ≤3 días
     → "El sistema predice que se acaba pronto" (usa el modelo ML)

La opción 2 es lo que hace que esto funcione DESDE EL DÍA 1 sin que el
dueño tenga que configurar min_stock por producto. La opción 3 entra en
juego cuando el modelo madura (~día 14+).

Uso:
    python manage.py send_low_stock_alerts
    python manage.py send_low_stock_alerts --tenant 1
    python manage.py send_low_stock_alerts --dry-run
"""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import F, Sum


class Command(BaseCommand):
    help = "Envía emails de alerta de stock bajo a los dueños de cada tenant."

    # Condición 2: cuántos días de stock disparan la alerta automática
    AUTO_MIN_DAYS = 2
    # Condición 3: predicción ≤ N días → alerta
    FORECAST_DAYS = 3
    # Cuántos días hacia atrás para calcular avg_daily
    AVG_DAILY_WINDOW = 14
    # Tope de alertas en el email (priorizando rotación). Si hay más, el email
    # las menciona como "y N productos más" con link al detalle. Esto evita
    # que el cliente reciba un email con 74 productos y se desmotive.
    MAX_ALERTS_IN_EMAIL = 30

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None,
                            help="Limita el envío a un tenant específico")
        parser.add_argument("--dry-run", action="store_true", default=False,
                            help="No envía emails, solo lista quiénes recibirían")

    def handle(self, *args, **options):
        from core.models import Tenant, User, AlertPreference

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

            # Respeta preferencias
            try:
                prefs = AlertPreference.objects.get(user=owner)
                if not prefs.stock_bajo:
                    self.stdout.write(f"  [skip] {owner.email} → stock_bajo apagado")
                    skipped += 1
                    continue
            except AlertPreference.DoesNotExist:
                pass

            all_alerts = self._compute_alerts(tenant)
            if not all_alerts:
                self.stdout.write(f"  [ok] tenant={tenant.id} sin alertas")
                continue

            total_count = len(all_alerts)
            # Cortar a top N priorizando rotación. all_alerts ya viene ordenado
            # (críticos primero, después por avg_daily desc, después por días).
            shown = all_alerts[:self.MAX_ALERTS_IN_EMAIL]
            truncated = max(0, total_count - len(shown))

            critical = [a for a in shown if a["priority"] == "critical"]
            warning = [a for a in shown if a["priority"] == "warning"]

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  [dry] {owner.email} → mostrando {len(shown)} de {total_count} "
                    f"({len(critical)} críticos, {len(warning)} warnings, +{truncated} más)"
                ))
                for a in shown[:10]:  # primeros 10 visibles
                    self.stdout.write(
                        f"      • {a['product_name'][:35]:<35s}  "
                        f"on_hand={a['on_hand']:>5.0f}  rot={a['avg_daily']:>5.1f}/d  "
                        f"reason={a['reason']:<8s}  days_left={a['days_left'] if a['days_left'] is not None else '—'}"
                    )
                continue

            from billing.email_renderers import render_low_stock_v2
            subject, plain, html = render_low_stock_v2(
                tenant=tenant,
                critical_alerts=critical,
                warning_alerts=warning,
                truncated_count=truncated,
            )

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
                    f"  [sent] {owner.email} → {len(alerts)} alertas"
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  [error] {owner.email}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal enviados: {sent} · saltados: {skipped}"
        ))

    def _compute_alerts(self, tenant):
        """Aplica las 3 reglas para un tenant y devuelve lista ordenada de alertas.

        Cada alerta es un dict con:
          product_name, sku, warehouse, on_hand, reason, threshold,
          avg_daily, days_left, priority
        """
        from inventory.models import StockItem
        from sales.models import SaleLine
        from forecast.models import Forecast

        today = date.today()

        # ── (a) avg_daily real basado en ventas últimos N días ─────────
        recent_window = today - timedelta(days=self.AVG_DAILY_WINDOW)
        recent_qs = (
            SaleLine.objects.filter(
                sale__tenant=tenant,
                sale__created_at__date__gte=recent_window,
            )
            .values("product_id")
            .annotate(total=Sum("qty"))
        )
        avg_daily_map = {
            row["product_id"]: float(row["total"] or 0) / self.AVG_DAILY_WINDOW
            for row in recent_qs
        }

        # ── (b) Predicciones del forecast ──────────────────────────────
        # Tomamos el día con menor days_to_stockout para cada producto
        # entre las predicciones futuras.
        fc_qs = (
            Forecast.objects.filter(
                tenant=tenant,
                forecast_date__gt=today,
                days_to_stockout__isnull=False,
                days_to_stockout__lte=self.FORECAST_DAYS,
            )
            .values("product_id", "warehouse_id", "days_to_stockout")
        )
        forecast_map = {}  # (pid, wid) → min_days
        for row in fc_qs:
            key = (row["product_id"], row["warehouse_id"])
            cur = forecast_map.get(key)
            if cur is None or row["days_to_stockout"] < cur:
                forecast_map[key] = row["days_to_stockout"]

        # ── (c) Recorrer cada StockItem y ver si dispara alguna regla ──
        items = (
            StockItem.objects
            .filter(tenant=tenant, product__is_active=True)
            .select_related("product", "warehouse")
        )

        alerts = []
        for item in items:
            on_hand = float(item.on_hand or 0)
            product = item.product
            warehouse_name = item.warehouse.name if item.warehouse else "—"
            avg_daily = avg_daily_map.get(product.id, 0.0)

            alert = self._build_alert(
                item=item,
                on_hand=on_hand,
                product=product,
                warehouse_name=warehouse_name,
                avg_daily=avg_daily,
                forecast_days=forecast_map.get((product.id, item.warehouse_id)),
            )
            if alert:
                alerts.append(alert)

        # Ordenar por (prioridad, rotación desc, días restantes asc):
        #   1. Críticos primero (priority "critical")
        #   2. Dentro del mismo nivel: los productos que MÁS rotan primero —
        #      si el cliente solo va a leer el top 30, deben ser los que
        #      más le duele al negocio si se quedan sin stock.
        #   3. Empate: el de menos días restantes primero.
        # Multiplicamos avg_daily por -1 para sort descendente en una key
        # que sort respeta como tuple ascendente.
        alerts.sort(key=lambda a: (
            0 if a["priority"] == "critical" else 1,
            -float(a.get("avg_daily") or 0),
            a["days_left"] if a["days_left"] is not None else 999,
        ))
        return alerts

    def _build_alert(self, item, on_hand, product, warehouse_name, avg_daily, forecast_days):
        """Aplica las 3 reglas en orden de prioridad y devuelve la alerta o None."""
        manual_min = float(product.min_stock or 0)

        # Stock 0 → siempre crítico (cualquiera sea la regla)
        if on_hand <= 0:
            return {
                "product_name": product.name,
                "sku": product.sku or "—",
                "warehouse": warehouse_name,
                "on_hand": on_hand,
                "reason": "stockout",
                "reason_text": "Sin stock",
                "threshold": None,
                "avg_daily": avg_daily,
                "days_left": 0,
                "priority": "critical",
            }

        # Regla 1: min_stock manual configurado
        if manual_min > 0 and on_hand <= manual_min:
            days_left = round(on_hand / avg_daily, 1) if avg_daily > 0 else None
            priority = "critical" if (days_left is not None and days_left <= 1) else "warning"
            return {
                "product_name": product.name,
                "sku": product.sku or "—",
                "warehouse": warehouse_name,
                "on_hand": on_hand,
                "reason": "manual",
                "reason_text": f"Bajo tu mínimo de {int(manual_min)}",
                "threshold": manual_min,
                "avg_daily": avg_daily,
                "days_left": days_left,
                "priority": priority,
            }

        # Regla 3 PRIMERO: forecast predice agotamiento ≤3 días
        # (Lo chequeamos antes que la regla 2 porque es más informado.)
        if forecast_days is not None:
            return {
                "product_name": product.name,
                "sku": product.sku or "—",
                "warehouse": warehouse_name,
                "on_hand": on_hand,
                "reason": "forecast",
                "reason_text": f"Predicción: se acaba en ~{forecast_days} día{'s' if forecast_days != 1 else ''}",
                "threshold": None,
                "avg_daily": avg_daily,
                "days_left": forecast_days,
                "priority": "critical" if forecast_days <= 1 else "warning",
            }

        # Regla 2: min_stock automático = avg_daily × AUTO_MIN_DAYS
        if avg_daily > 0:
            auto_min = avg_daily * self.AUTO_MIN_DAYS
            if on_hand <= auto_min:
                days_left = round(on_hand / avg_daily, 1)
                priority = "critical" if days_left <= 1 else "warning"
                return {
                    "product_name": product.name,
                    "sku": product.sku or "—",
                    "warehouse": warehouse_name,
                    "on_hand": on_hand,
                    "reason": "auto",
                    "reason_text": f"Te alcanza para {days_left} día{'s' if days_left != 1 else ''} (vendés {round(avg_daily, 1)}/día)",
                    "threshold": round(auto_min, 1),
                    "avg_daily": avg_daily,
                    "days_left": days_left,
                    "priority": priority,
                }

        return None
