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
from django.db.models import Count, F, Q, Sum


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
    # ── Gates de madurez para la regla #3 (forecast) ──────────────────
    # En las primeras semanas el modelo predice cualquier cosa (puede
    # decir "vasos chicos se acaba en 1 día" cuando tenés 236). Si
    # mandamos esas alertas el cliente pierde confianza en el sistema
    # desde el primer email. La regla #3 se activa POR PRODUCTO solo
    # cuando su modelo tiene madurez suficiente.
    FORECAST_MIN_DATA_POINTS = 14         # >=14 días de historial del producto
    # "Se vende sin stock cargado": vendio al menos estos dias en la ventana y
    # ninguno cerro con stock. Ver _compute_alerts.
    SIN_CONTROL_DIAS = 60
    SIN_CONTROL_MIN_DIAS = 3
    # Cuantos dias cubre la cantidad sugerida en el correo.
    DIAS_A_CUBRIR = 7
    FORECAST_REJECTED_CONFIDENCE = "very_low"   # excluir modelos very_low

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None,
                            help="Limita el envío a un tenant específico")
        parser.add_argument("--dry-run", action="store_true", default=False,
                            help="No envía emails, solo lista quiénes recibirían")

    def handle(self, *args, **options):
        # Heartbeat para que una alerta rota se vea en /health/deep/ en vez de
        # descubrirse porque el dueno comenta que dejo de recibir el correo.
        # 36h de tolerancia: es diaria, con margen para un dia fallado.
        # El dry-run no registra: es una consulta, no la corrida real.
        if options.get("dry_run"):
            return self._handle(*args, **options)
        from core.cron_utils import cron_wrapper
        with cron_wrapper("inventory.low_stock_alerts", max_age_min=36 * 60):
            return self._handle(*args, **options)

    def _handle(self, *args, **options):
        from core.models import Tenant, User, AlertPreference

        tenant_id = options.get("tenant")
        dry_run = options.get("dry_run", False)

        tenants = Tenant.objects.filter(is_active=True)
        if tenant_id:
            tenants = tenants.filter(id=tenant_id)

        sent = 0
        skipped = 0
        for tenant in tenants:
            # Duenos Y encargados que la tengan encendida, no solo el primer
            # dueno: el que hace las compras suele ser el encargado. La regla
            # vive en core.alert_recipients para que todas las alertas usen la
            # misma y no se implemente distinto en cada comando.
            from core.alert_recipients import destinatarios
            usuarios = destinatarios(tenant, "stock_bajo")
            if not usuarios:
                self.stdout.write(f"  [skip] tenant={tenant.id} sin destinatarios")
                skipped += 1
                continue

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
                    f"  [dry] {len(usuarios)} destinatario(s): "
                    f"{', '.join(u.email for u in usuarios)}"
                ))
                self.stdout.write(self.style.WARNING(
                    f"        mostrando {len(shown)} de {total_count} "
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
                sin_control=getattr(self, "sin_control_por_tenant", {}).get(tenant.id, []),
            )

            # Un correo por persona, no uno con todos en copia: cada quien ve
            # su propia alerta y puede darse de baja sin afectar al resto.
            # Y si el servidor rechaza una direccion, las demas igual salen.
            for u in usuarios:
                try:
                    send_mail(
                        subject=subject,
                        message=plain,
                        html_message=html,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                           "Pulstock <noreply@pulstock.cl>"),
                        recipient_list=[u.email],
                        fail_silently=False,
                    )
                    sent += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"  [sent] {u.email} → {len(shown)} alertas"
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"  [error] {u.email}: {e}"
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
        # Uso real (29/10/26): DailySales trae tambien lo que se consume por
        # receta. Con solo las ventas directas, un insumo como la leche daba
        # 0 por dia y el correo no podia decir cuanto se usa ni cuanto pedir.
        # Se toma el mayor de los dos para no perder ventas del dia en curso.
        from forecast.models import DailySales
        uso_qs = (
            DailySales.objects.filter(tenant=tenant, date__gte=recent_window, date__lt=today)
            .values("product_id").annotate(total=Sum("qty_sold"))
        )
        for row in uso_qs:
            uso = float(row["total"] or 0) / self.AVG_DAILY_WINDOW
            if uso > avg_daily_map.get(row["product_id"], 0.0):
                avg_daily_map[row["product_id"]] = uso

        # Productos que se venden SIN stock cargado (29/10/26). El Te vendio
        # 21 en dos semanas y en 60 dias nunca cerro un dia con stock: no hay
        # nada que reponer, es inventario que no se registra. Avisarlo como
        # "critico" todos los dias es ruido; va a una nota aparte.
        desde_60 = today - timedelta(days=self.SIN_CONTROL_DIAS)
        sin_control = set()
        for row in (
            DailySales.objects.filter(tenant=tenant, date__gte=desde_60, qty_sold__gt=0)
            .values("product_id")
            .annotate(dias=Count("id"), con_stock=Count("id", filter=Q(closing_stock__gt=0)))
        ):
            if row["dias"] >= self.SIN_CONTROL_MIN_DIAS and row["con_stock"] == 0:
                sin_control.add(row["product_id"])
        self.sin_control_por_tenant = getattr(self, "sin_control_por_tenant", {})
        self.sin_control_por_tenant[tenant.id] = []

        # ── (b) Predicciones del forecast — CON GATE DE MADUREZ ────────
        # IMPORTANTE: solo confiamos en la predicción cuando el modelo del
        # producto tiene suficiente madurez. Si no, descartamos esa alerta
        # porque genera ruido (ej: "236 vasos se acaban en 1 día" → falso).
        #
        # Cargamos primero los modelos activos del tenant con su metadata.
        # Si el modelo tiene <14 días de datos o confianza very_low, NO
        # aplicamos la regla #3 a ese producto. Las reglas #1 (manual) y
        # #2 (auto basado en venta real) siguen funcionando para él.
        from forecast.models import ForecastModel
        mature_keys = set()
        for m in ForecastModel.objects.filter(
            tenant=tenant, is_active=True,
        ).only("product_id", "warehouse_id", "data_points", "confidence_label"):
            data_points = m.data_points or 0
            conf = m.confidence_label or ""
            if (
                data_points >= self.FORECAST_MIN_DATA_POINTS
                and conf != self.FORECAST_REJECTED_CONFIDENCE
            ):
                mature_keys.add((m.product_id, m.warehouse_id))

        # Cargamos solo predicciones de productos cuyo modelo es maduro.
        forecast_map = {}  # (pid, wid) → min_days
        if mature_keys:
            fc_qs = (
                Forecast.objects.filter(
                    tenant=tenant,
                    forecast_date__gt=today,
                    days_to_stockout__isnull=False,
                    days_to_stockout__lte=self.FORECAST_DAYS,
                )
                .values("product_id", "warehouse_id", "days_to_stockout")
            )
            for row in fc_qs:
                key = (row["product_id"], row["warehouse_id"])
                if key not in mature_keys:
                    continue  # gate: modelo no maduro, ignorar predicción
                cur = forecast_map.get(key)
                if cur is None or row["days_to_stockout"] < cur:
                    forecast_map[key] = row["days_to_stockout"]

        # Lo que se espera usar en los proximos DIAS_A_CUBRIR dias, segun lo
        # publicado (29/10/26). Es lo que decide cuanto pedir: el promedio de
        # 14 dias no ve los dias fuertes que vienen (la leche "alcanza 2 dias"
        # con un promedio que decia 5).
        proximos = {}
        for row in (
            Forecast.objects.filter(
                tenant=tenant, forecast_date__gt=today,
                forecast_date__lte=today + timedelta(days=self.DIAS_A_CUBRIR),
            ).values("product_id", "warehouse_id").annotate(total=Sum("qty_predicted"))
        ):
            proximos[(row["product_id"], row["warehouse_id"])] = float(row["total"] or 0)

        # ── (c) Recorrer cada StockItem y ver si dispara alguna regla ──
        #
        # Se EXCLUYEN los productos con receta. Un capuccino, un latte o un
        # cortado se preparan al momento: su on_hand es 0 siempre, por diseno,
        # y eso no es un quiebre. Sin este filtro la alerta avisaba de 82
        # productos —toda la carta de cafeteria incluida— y era puro ruido:
        # es la razon real por la que esta alerta quedo pausada en may-2026.
        #
        # Lo que SI hay que vigilar de un capuccino es su leche y su cafe, y
        # esos son productos sin receta que ya entran por su cuenta.
        items = (
            StockItem.objects
            .filter(tenant=tenant, product__is_active=True)
            .exclude(product__recipe__isnull=False)
            .select_related("product", "warehouse")
        )

        alerts = []
        for item in items:
            on_hand = float(item.on_hand or 0)
            product = item.product
            warehouse_name = item.warehouse.name if item.warehouse else "—"
            avg_daily = avg_daily_map.get(product.id, 0.0)
            if product.id in sin_control and on_hand <= 0:
                self.sin_control_por_tenant[tenant.id].append(product.name)
                continue

            alert = self._build_alert(
                item=item,
                on_hand=on_hand,
                product=product,
                warehouse_name=warehouse_name,
                avg_daily=avg_daily,
                forecast_days=forecast_map.get((product.id, item.warehouse_id)),
            )
            if alert:
                alert["proximos_dias"] = proximos.get((product.id, item.warehouse_id))
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

        # Stock 0 → crítico, PERO solo si el producto se mueve.
        #
        # Un producto sin stock y sin una sola venta en la ventana no es un
        # quiebre: es un producto descontinuado. Avisar de eso todos los dias
        # es exactamente lo que hace que el dueno deje de abrir el correo.
        # Medido en Marbrava (ago-2026): de 24 "quiebres" solo 8 se vendian;
        # los otros 16 eran cafes de especialidad y golosinas que salieron de
        # carta hace meses.
        #
        # Si el dueno le puso un min_stock manual, si avisamos aunque no rote:
        # ese minimo es una decision explicita suya (regla 1, mas abajo).
        if on_hand <= 0 and avg_daily <= 0 and manual_min <= 0:
            return None

        # Stock 0 → siempre crítico (cualquiera sea la regla)
        if on_hand <= 0:
            return {
                "product_name": product.name,
                "sku": product.sku or "—",
                "unit": (product.unit or "UN").upper(),
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
                "unit": (product.unit or "UN").upper(),
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
                "unit": (product.unit or "UN").upper(),
                "warehouse": warehouse_name,
                "on_hand": on_hand,
                "reason": "forecast",
                "reason_text": f"Predicción: se acaba en ~{forecast_days} día{'s' if forecast_days != 1 else ''}",
                "threshold": None,
                "avg_daily": avg_daily,
                "days_left": forecast_days,
                "priority": "critical" if forecast_days <= 1 else "warning",
            }

        # Regla 2: minimo automatico.
        #
        # Antes era `avg_daily x 2`: dos dias de venta, plano para todo. Eso
        # ignoraba dos cosas que deciden si la alerta sirve o llega tarde:
        #   · la variabilidad (10±1 y 10±8 recibian el mismo minimo)
        #   · el lead time (con proveedor de 5 dias, avisar a los 2 es tarde)
        #
        # Ahora usa el minimo que recalcula `recalcular_minimos` cada noche:
        # consumo durante el lead time + colchon por variabilidad. Si todavia
        # no se calculo —producto nuevo, primera noche— cae a la regla vieja
        # para no dejar de avisar mientras tanto.
        # La reja no puede ser `avg_daily > 0`.
        #
        # Ese promedio son los ultimos 14 dias, y para el papel higienico —el
        # producto del que se quejo Mario— vale CERO: gasta 5 unidades en 80
        # dias. Con esa condicion, calcular su minimo no servia de nada porque
        # la regla no llegaba a evaluarse nunca.
        #
        # Alcanza con que exista un minimo calculado: `recalcular_minimos` solo
        # lo pone si hubo consumo real. El filtro de descontinuados de mas
        # arriba sigue intacto, asi que esto no revive productos muertos: los
        # que estan en cero y no rotan se siguen callando.
        calculado = getattr(item, "min_stock_auto", None)
        if calculado or avg_daily > 0:
            auto_min = float(calculado) if calculado else avg_daily * self.AUTO_MIN_DAYS
            if on_hand <= auto_min:
                days_left = round(on_hand / avg_daily, 1) if avg_daily > 0 else None
                priority = "critical" if (days_left is not None and days_left <= 1) else "warning"
                if days_left is not None:
                    texto = (
                        f"Te alcanza para {days_left} día{'s' if days_left != 1 else ''} "
                        f"(vendes {round(avg_daily, 1)}/dia)"
                    )
                else:
                    # Rotacion lenta: "te alcanza para 0 dias" seria falso y
                    # alarmante. Lo util es decirle que ya toca reponer.
                    texto = f"Quedan {round(on_hand, 1)} y conviene reponer"
                return {
                    "product_name": product.name,
                    "sku": product.sku or "—",
                "unit": (product.unit or "UN").upper(),
                    "warehouse": warehouse_name,
                    "on_hand": on_hand,
                    "reason": "auto",
                    "reason_text": texto,
                    "threshold": round(auto_min, 1),
                    "avg_daily": avg_daily,
                    "days_left": days_left,
                    "priority": priority,
                }

        return None
