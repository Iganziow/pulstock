"""
billing/email_renderers.py
==========================
Renderiza los templates Django de email con el contexto correcto.

Este módulo reemplaza las funciones _billing_html / _email_callout / _email_data_row
de billing/tasks.py por render_to_string() con los templates de
apps/api/billing/templates/emails/*.html.

USO DESDE tasks.py:

    from billing.email_renderers import (
        render_welcome, render_trial_reminder, render_renewal_reminder,
        render_payment_failed, render_suspension, render_payment_recovered,
        render_trial_converted, render_trial_expired,
    )

    def _send_welcome_email(user, tenant, plan):
        subject, plain, html = render_welcome(user, tenant, plan)
        _send_email_safe(user.email, subject, plain, html)

TONE → colores (para context del base.html):
    indigo  → #4F46E5 / #EEF2FF
    green   → #16A34A / #ECFDF5
    red     → #DC2626 / #FEF2F2
    amber   → #D97706 / #FFFBEB
    black   → #18181B / #F4F4F5
"""

from datetime import timedelta
from django.template.loader import render_to_string
from django.utils import timezone


APP_URL = "https://app.pulstock.cl"
LANDING_URL = "https://pulstock.cl"
SETTINGS_URL = f"{APP_URL}/dashboard/settings?tab=plan"
BRAND = "Pulstock"
SUPPORT_EMAIL = "pulstock.admin@gmail.com"
LOGO_URL = "https://pulstock.cl/email-logo.png?v=20260424"

# Paleta de la direccion «Carta». Los colores son mas profundos que los de la
# interfaz a proposito: sobre papel calido (#FCFBF9) un indigo de boton web se
# ve estridente, y los tintes tienen que leerse como una mancha de tinta, no
# como un fondo de UI. Los grises estan sesgados hacia el indigo — un gris
# neutro se lee como no elegido.
#
# `cta_grad1/2` se conservan porque algun renderer podria pasarlos; la
# plantilla ya no los usa (los degradados son lo primero que Outlook descarta).
TONES = {
    "indigo": {"eyebrow_bg": "#EFEDFB", "eyebrow_fg": "#4338CA",
               "cta_bg": "#4338CA", "cta_grad1": "#4338CA", "cta_grad2": "#4338CA"},
    "green":  {"eyebrow_bg": "#EAF4EC", "eyebrow_fg": "#15803D",
               "cta_bg": "#15803D", "cta_grad1": "#15803D", "cta_grad2": "#15803D"},
    "red":    {"eyebrow_bg": "#FBEDEB", "eyebrow_fg": "#AF2318",
               "cta_bg": "#AF2318", "cta_grad1": "#AF2318", "cta_grad2": "#AF2318"},
    "amber":  {"eyebrow_bg": "#FAF1E4", "eyebrow_fg": "#A65B07",
               "cta_bg": "#A65B07", "cta_grad1": "#A65B07", "cta_grad2": "#A65B07"},
    "black":  {"eyebrow_bg": "#EDEBE6", "eyebrow_fg": "#191825",
               "cta_bg": "#191825", "cta_grad1": "#191825", "cta_grad2": "#191825"},
}


def _base_ctx(tone="indigo", **extra):
    ctx = {
        "logo_url": LOGO_URL,
        "unsubscribe_url": f"{APP_URL}/dashboard/settings?tab=alertas",
    }
    ctx.update(TONES[tone])
    ctx.update(extra)
    return ctx


def _fmt_clp(n):
    return f"${n:,.0f} CLP".replace(",", ".")


# ─────────── 01 Welcome ───────────
def render_welcome(user, tenant, plan, next_charge=None):
    next_charge = next_charge or (timezone.now() + timedelta(days=30)).date()
    name = (user.first_name or user.username or "").strip()
    subject = f"🎉 Tu cuenta de {BRAND} está lista — {tenant.name}"
    ctx = _base_ctx(
        tone="indigo",
        subject_line=subject,
        eyebrow="Bienvenida · Cuenta activa",
        hero_title=f"Tu cuenta de {BRAND} está lista{', ' + name if name else ''}",
        subtitle="Gracias por unirte. Te dejamos tus datos de acceso y 3 primeros pasos para empezar a operar en minutos.",
        user=user, tenant=tenant, plan=plan,
        next_charge=next_charge,
        cta_text="Abrir mi dashboard",
        cta_url=f"{APP_URL}/dashboard",
        secondary_text="Descargar app móvil para vendedores",
        secondary_url=f"{LANDING_URL}/descargas",
        steps=[
            {"title": "Carga tus productos",
             "body": "Ingresa tu catálogo en <strong style='color:#18181B;'>Catálogo</strong>. Si ya tienes un Excel, puedes importarlo en bloque desde el mismo módulo."},
            {"title": "Realiza tu primera venta",
             "body": "Abre el <strong style='color:#18181B;'>Punto de Venta</strong> y simula una venta para familiarizarte con el flujo de cobro y boleta."},
            {"title": "Configura tu impresora térmica",
             "body": "En <strong style='color:#18181B;'>Configuración › Impresoras</strong> puedes emparejar impresoras USB o de red en segundos."},
        ],
    )
    html = render_to_string("emails/welcome.html", ctx)
    plain = (
        f"¡Bienvenido a {BRAND}, {name}!\n\n"
        f"Tu cuenta está activa.\n"
        f"Negocio: {tenant.name}\nUsuario: {user.username}\nPlan: {plan.name}\n\n"
        f"Inicia sesión en {APP_URL}/login\n\n"
        f"Soporte: {SUPPORT_EMAIL}"
    )
    return subject, plain, html


# ─────────── 02 Trial reminder ───────────
def render_trial_reminder(sub, days_left):
    plan = sub.plan
    plan.price_formatted = _fmt_clp(plan.price_clp) + "/mes"
    subject = f"Tu prueba vence en {days_left} {'día' if days_left == 1 else 'días'} — {BRAND}"
    ctx = _base_ctx(
        tone="amber",
        subject_line=subject,
        eyebrow=f"Prueba · {days_left} días restantes",
        hero_title=f"Tu prueba gratuita termina {'pronto' if days_left == 1 else f'en {days_left} días'}",
        subtitle="Agrega un método de pago ahora para no perder el acceso a tus productos, ventas y reportes.",
        days_left=days_left,
        plan=plan,
        trial_ends_at=sub.trial_ends_at,
        cta_text="Agregar método de pago",
        cta_url=SETTINGS_URL,
        secondary_text="Seguir con el plan gratuito",
        secondary_url=f"{APP_URL}/dashboard",
    )
    html = render_to_string("emails/trial_reminder.html", ctx)
    plain = f"Tu prueba de {BRAND} vence en {days_left} días. Gestiona en {SETTINGS_URL}"
    return subject, plain, html


# ─────────── 03 Renewal reminder ───────────
def render_renewal_reminder(sub, days_left, payment_method=None):
    """Email de renovación próxima.

    payment_method: string formateado (ej. "Visa ···· 4829") si la sub tiene
      tarjeta registrada. Si es None, usamos un fallback genérico.
    """
    plan = sub.plan
    plan.price_formatted = _fmt_clp(plan.price_clp)
    end = sub.current_period_end
    next_end = end + timedelta(days=30) if end else None
    period_range = f"{end.strftime('%d/%m')} → {next_end.strftime('%d/%m/%Y')}" if end and next_end else "—"
    # Fallback si no hay tarjeta registrada
    payment_method_display = payment_method or "Tu método de pago registrado"
    subject = f"Tu suscripción se renueva en {days_left} días — {BRAND}"
    ctx = _base_ctx(
        tone="indigo",
        subject_line=subject,
        eyebrow=f"Renovación · En {days_left} días",
        hero_title=f"Renovaremos tu suscripción el {end.strftime('%d de %B').lower() if end else 'próximamente'}",
        subtitle="No tienes que hacer nada: cobraremos automáticamente tu método de pago registrado.",
        plan=plan, user=sub.tenant,
        current_period_end=end,
        payment_method=payment_method_display,
        period_range=period_range,
        cta_text="Ver mi suscripción",
        cta_url=SETTINGS_URL,
        secondary_text="Cambiar método de pago",
        secondary_url=SETTINGS_URL,
    )
    html = render_to_string("emails/renewal_reminder.html", ctx)
    plain = f"Renovación en {days_left} días. Monto: {plan.price_formatted}. {SETTINGS_URL}"
    return subject, plain, html


# ─────────── 04 Payment failed ───────────
def render_payment_failed(sub, invoice_number, failure_reason=None,
                          payment_method=None, access_until=None):
    """Email de pago fallido.

    failure_reason: mensaje del gateway (ej. "Tarjeta vencida"). Si es None,
      usamos un mensaje genérico para no inventar un motivo.
    payment_method: "Visa ···· 4829" o None. Si None, usamos "Tu tarjeta".
    access_until: fecha hasta la que el cliente mantiene acceso antes de
      suspensión. Si None, se estima 3 días desde hoy (grace period común).
    """
    plan = sub.plan
    plan.price_formatted = _fmt_clp(plan.price_clp)
    access_until = access_until or (timezone.now() + timedelta(days=3))

    # Construir el título y body del callout sin inventar datos.
    if payment_method:
        card_title = f"{payment_method} fue rechazada"
    else:
        card_title = "El cobro fue rechazado"

    if failure_reason:
        card_body = (
            f"Motivo informado: <em>{failure_reason}</em>. "
            f"Volveremos a intentar el cobro en 48 horas. Si falla 3 veces, "
            f"tu cuenta se suspenderá temporalmente."
        )
    else:
        card_body = (
            "El banco emisor no autorizó la transacción. "
            "Volveremos a intentar el cobro en 48 horas. Si falla 3 veces, "
            "tu cuenta se suspenderá temporalmente."
        )

    subject = f"⚠️ No pudimos procesar tu pago — {BRAND}"
    ctx = _base_ctx(
        tone="red",
        subject_line=subject,
        eyebrow=f"Pago · Intento {sub.payment_retry_count} de 3",
        hero_title="No pudimos procesar tu pago",
        subtitle=(
            f"Actualiza tu método de pago antes del "
            f"{access_until.strftime('%d de %B').lower()} para mantener tu acceso."
        ),
        payment_failed_title=card_title,
        payment_failed_body=card_body,
        plan=plan,
        invoice_number=invoice_number,
        retry_progress=f"{sub.payment_retry_count} de 3",
        next_retry_at=sub.next_retry_at,
        access_until=access_until,
        cta_text="Actualizar método de pago",
        cta_url=SETTINGS_URL,
        secondary_text="Ver detalle de la factura",
        secondary_url=f"{APP_URL}/dashboard/settings?tab=facturas",
    )
    html = render_to_string("emails/payment_failed.html", ctx)
    plain = f"Pago fallido. Actualiza en {SETTINGS_URL}"
    return subject, plain, html


# ─────────── 05 Suspension ───────────
def render_suspension(sub, amount_due=None):
    amount_due = amount_due or _fmt_clp(sub.plan.price_clp)
    suspended_at = sub.suspended_at or timezone.now()
    data_until = suspended_at + timedelta(days=30)
    subject = f"🔒 Cuenta suspendida — {BRAND}"
    ctx = _base_ctx(
        tone="black",
        subject_line=subject,
        eyebrow="Cuenta · Suspendida",
        hero_title="Tu cuenta ha sido suspendida",
        subtitle="Intentamos cobrar tu suscripción 3 veces sin éxito. Tu acceso está pausado, pero tus datos siguen a salvo por 30 días.",
        suspended_at=suspended_at,
        retry_progress="3 de 3",
        amount_due=amount_due,
        data_until=data_until,
        cta_text="Reactivar mi cuenta",
        cta_url=SETTINGS_URL,
        secondary_text="Contactar a soporte",
        secondary_url=f"mailto:{SUPPORT_EMAIL}",
    )
    html = render_to_string("emails/suspension.html", ctx)
    plain = f"Cuenta suspendida. Datos hasta {data_until.strftime('%d/%m/%Y')}. Reactiva en {SETTINGS_URL}"
    return subject, plain, html


# ─────────── 06 Payment recovered ───────────
def render_payment_recovered(sub, invoice_number, amount=None,
                             payment_method=None, charged_at=None):
    """Email de pago recuperado tras retry exitoso.

    payment_method: string (ej. "Tarjeta ···· 6623") o None. Si None,
      el body omite la mención de tarjeta.
    """
    amount = amount or sub.plan.price_clp
    amount_formatted = _fmt_clp(amount)
    charged_at = charged_at or timezone.now()

    if payment_method:
        recovered_body = (
            f"Cargado a <span style='font-family:JetBrains Mono,monospace;'>"
            f"{payment_method}</span> el {charged_at.strftime('%d/%m/%Y a las %H:%M')}."
        )
    else:
        recovered_body = f"Cobro procesado el {charged_at.strftime('%d/%m/%Y a las %H:%M')}."

    subject = f"✅ Pago procesado — {BRAND}"
    ctx = _base_ctx(
        tone="green",
        subject_line=subject,
        eyebrow="Pago · Procesado",
        hero_title="¡Listo! Procesamos tu pago correctamente",
        subtitle="Tu suscripción sigue activa y tienes acceso completo a todas las funciones.",
        recovered_title=f"Cobro exitoso · {amount_formatted}",
        recovered_body=recovered_body,
        plan=sub.plan,
        invoice_number=invoice_number,
        amount_formatted=amount_formatted,
        next_charge=sub.current_period_end,
        cta_text="Ir al dashboard",
        cta_url=f"{APP_URL}/dashboard",
        secondary_text="Descargar boleta",
        secondary_url=f"{APP_URL}/dashboard/settings?tab=facturas",
    )
    html = render_to_string("emails/payment_recovered.html", ctx)
    plain = f"Pago procesado: {amount_formatted}. Próximo cobro: {sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'}."
    return subject, plain, html


# ─────────── 07 Trial converted ───────────
def render_trial_converted(sub, payment_method=None):
    plan = sub.plan
    amount_formatted = _fmt_clp(plan.price_clp)
    features = [
        "Productos ilimitados", "Múltiples locales",
        "Usuarios y roles", "Reportes avanzados",
        "Análisis ABC", "Boleta electrónica",
    ]
    feature_rows = [features[i:i+2] for i in range(0, len(features), 2)]
    subject = f"✅ Suscripción activada — {BRAND}"
    ctx = _base_ctx(
        tone="green",
        subject_line=subject,
        eyebrow="Suscripción · Activada",
        hero_title="Tu suscripción está activa",
        subtitle="Tu período de prueba terminó y ya eres cliente Pro. Disfruta todas las funciones sin límites.",
        converted_title=f"{plan.name} · Activado",
        converted_body=f"Primer cobro de <strong>{amount_formatted}</strong> procesado correctamente.",
        plan=plan,
        # Fallback: si no hay tarjeta registrada, mostrar texto genérico en vez
        # de dejar el campo vacío (rompería el diseño del data_row).
        payment_method=payment_method or "Tu método de pago",
        first_charge_formatted=amount_formatted,
        next_charge=sub.current_period_end,
        feature_rows=feature_rows,
        cta_text="Ir al dashboard",
        cta_url=f"{APP_URL}/dashboard",
        secondary_text="Ver mi primera factura",
        secondary_url=f"{APP_URL}/dashboard/settings?tab=facturas",
    )
    html = render_to_string("emails/trial_converted.html", ctx)
    plain = f"Suscripción activada: {plan.name}. Próximo cobro: {sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'}."
    return subject, plain, html


# ─────────── 08 Trial expired ───────────
def render_trial_expired(sub, products_count=0, products_limit=None):
    """Email cuando el trial vence y NO hay tarjeta registrada.

    Pulstock no tiene plan Free, así que la cuenta queda CANCELLED y el
    cliente pierde acceso. El copy invita a reactivar agregando tarjeta.
    Los datos se conservan 30 días según política de retención.
    """
    previous_plan_name = sub.plan.name
    previous_plan_price = _fmt_clp(sub.plan.price_clp)

    # `products_limit` ya no aplica (no hay plan Free); lo ignoramos para
    # mantener la firma backwards-compat pero no se muestra al cliente.
    _ = products_limit

    # Cuenta cuántos días le quedan al cliente para reactivar antes de
    # que se eliminen los datos (política: 30 días desde la cancelación).
    cancelled_at = sub.cancelled_at or timezone.now()
    data_retention_until = cancelled_at + timedelta(days=30)

    subject = f"Tu prueba terminó — {BRAND}"
    ctx = _base_ctx(
        tone="amber",
        subject_line=subject,
        eyebrow="Prueba · Finalizada",
        hero_title="Tu prueba terminó · Reactivá tu cuenta",
        subtitle=(
            f"Tu período de prueba de 7 días en {previous_plan_name} ya venció. "
            f"Para seguir usando {BRAND}, agrega un método de pago. "
            f"Tus datos se conservan hasta el "
            f"{data_retention_until.strftime('%d/%m/%Y')}."
        ),
        previous_plan_name=previous_plan_name,
        previous_plan_price=previous_plan_price,
        products_count=products_count,
        data_retention_until=data_retention_until,
        cta_text=f"Reactivar con {previous_plan_name}",
        cta_url=SETTINGS_URL,
        secondary_text="Ver otros planes",
        secondary_url=f"{LANDING_URL}/precios",
    )
    html = render_to_string("emails/trial_expired.html", ctx)
    plain = (
        f"Tu prueba de {BRAND} terminó. Para seguir usando la app, "
        f"agregá tu método de pago: {SETTINGS_URL}\n\n"
        f"Tus datos se conservan hasta el {data_retention_until.strftime('%d/%m/%Y')}."
    )
    return subject, plain, html


# ─────────── 09 ABC weekly ───────────
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha(d, con_anio=False):
    """"4 ago" / "2 nov 2026": strftime('%b') sale en ingles."""
    s = f"{d.day} {MESES[d.month - 1]}"
    return f"{s} {d.year}" if con_anio else s


def _clp(n):
    """"$6.624.020": la cifra completa, como la ve el dueno en su caja. "$6.6M"
    obliga a convertir y mezcla el punto decimal ingles con el de miles."""
    return f"${float(n or 0):,.0f}".replace(",", ".")


def _margen_txt(i):
    """Que decir del margen de un producto del ABC.

    Con costo completo, el registrado. Si el costo no es confiable (se vendio
    sin costo cargado o con la receta a medias), NO se muestra el registrado:
    saldria 100% o negativo. Va el estimado con el costo de hoy, marcado con
    ≈, o "—" si tampoco hay costo de hoy."""
    if i.get("cost_complete", True) and i.get("margin_pct") not in (None, ""):
        return f"{float(i['margin_pct']):.0f}%", False
    est = i.get("margin_pct_at_current_cost")
    if est not in (None, ""):
        return f"≈{float(est):.0f}%", True
    return "—", True


def render_abc_weekly(tenant, date_from, date_to, items_a, items_b, items_c,
                      total_revenue, total_profit, semana=None, meta=None):
    margin_pct = (total_profit / total_revenue * 100) if total_revenue else 0
    products_count = len(items_a) + len(items_b) + len(items_c)
    rev_a = sum(float(i["revenue"]) for i in items_a)
    rev_b = sum(float(i["revenue"]) for i in items_b)
    rev_c = sum(float(i["revenue"]) for i in items_c)
    pct = lambda v: round(v / total_revenue * 100) if total_revenue else 0

    hay_estimados = False

    def _prep(items, cls):
        nonlocal hay_estimados
        filas = []
        for i in items:
            margen, estimado = _margen_txt(i)
            hay_estimados = hay_estimados or estimado
            filas.append({
                "name": i["product_name"] or "(sin nombre)",
                "sku": i.get("sku") or "—",
                # El Chocolate Premium se vende por gramo: "3.303" a secas se
                # lee como unidades. _cantidad lo pasa a "3,3 kg".
                "units": _cantidad(i.get("qty") or i.get("units") or 0, i.get("unit")),
                "revenue_formatted": _clp(i["revenue"]),
                "margin_txt": margen,
                "cost_note": i.get("cost_note") or "",
                "cls": cls,
            })
        return filas

    # Utilidad con costo incompleto detras: decirlo, no inflarla en silencio.
    nota_utilidad = ""
    if meta and int(meta.get("cost_incomplete_products") or 0):
        nota_utilidad = (
            f"{meta['cost_incomplete_products']} productos "
            f"({_clp(meta['cost_incomplete_revenue'])} de venta) se vendieron sin costo cargado "
            f"o con la receta incompleta: la utilidad real es menor."
        )

    sem = None
    if semana and semana.get("actual"):
        a, ant, var = semana["actual"], semana["anterior"], semana.get("variacion_pct")
        if var is None:
            comparacion = "sin semana anterior para comparar"
        else:
            comparacion = f"{'+' if var >= 0 else '−'}{abs(var):.0f}% contra la semana anterior ({_clp(ant['total'])})"
        sem = {
            "rango": f"{_fecha(a['desde'])} al {_fecha(a['hasta'])}",
            "total": _clp(a["total"]),
            "boletas": a["boletas"],
            "comparacion": comparacion,
            "sube": var is not None and var >= 0,
        }

    subject = f"Reporte semanal — {tenant.name} · semana del {_fecha(date_to - timedelta(days=6))}"
    ctx = _base_ctx(
        tone="indigo",
        subject_line=subject,
        eyebrow="Reporte · semanal",
        hero_title="Lo que más vendiste en los últimos 90 días",
        subtitle=f"{tenant.name} · {_fecha(date_from)} al {_fecha(date_to, con_anio=True)}. "
                 f"{len(items_a)} productos concentran el {pct(rev_a)}% de los ingresos.",
        semana=sem,
        kpis={
            "revenue_formatted": _clp(total_revenue),
            "revenue_delta": "ingresos de 90 días",
            "profit_formatted": _clp(total_profit),
            "margin_pct": f"{margin_pct:.0f}",
            "margin_sublabel": f"Margen {margin_pct:.0f}%",
            "products_count": f"{products_count}",
        },
        nota_utilidad=nota_utilidad,
        class_counts={"a_count": len(items_a), "b_count": len(items_b), "c_count": len(items_c)},
        class_bars={"a_pct": pct(rev_a), "b_pct": pct(rev_b), "c_pct": pct(rev_c)},
        items_a=_prep(items_a[:5], "A"),
        items_b=_prep(items_b[:3], "B"),
        hay_estimados=hay_estimados,
        cta_text="Ver reporte completo",
        cta_url=f"{APP_URL}/dashboard/reports/abc-analysis",
        pie_corto=True,
    )
    html = render_to_string("emails/abc_weekly.html", ctx)

    lineas = [f"Reporte semanal — {tenant.name}"]
    if sem:
        lineas.append(f"Semana del {sem['rango']}: {sem['total']} en {sem['boletas']} boletas, {sem['comparacion']}.")
    lineas.append(f"Últimos 90 días ({_fecha(date_from)} al {_fecha(date_to, con_anio=True)}): "
                  f"ingresos {_clp(total_revenue)}, utilidad {_clp(total_profit)} (margen {margin_pct:.0f}%), "
                  f"{products_count} productos.")
    if nota_utilidad:
        lineas.append(nota_utilidad)
    lineas.append("Los que más venden:")
    for f in ctx["items_a"]:
        lineas.append(f"  {f['name']}: {f['revenue_formatted']} · {f['units']} · margen {f['margin_txt']}")
    if hay_estimados:
        lineas.append("≈ margen estimado con el costo de hoy (se vendió sin costo cargado).")
    lineas.append(f"Ver reporte completo: {APP_URL}/dashboard/reports/abc-analysis")
    plain = chr(10).join(lineas)
    return subject, plain, html


# ─────────── 10 Low stock ───────────
def render_low_stock(tenant, critical_items, low_items, snapshot_at=None):
    snapshot_at = snapshot_at or timezone.now()

    def _prep(stock_items):
        return [{
            "name": si.product.name,
            "sku": si.product.sku or "—",
            "warehouse": si.warehouse.name if si.warehouse else "—",
            "on_hand": int(si.on_hand),
            "min": int(si.product.min_stock),
            "deficit": int(si.product.min_stock - si.on_hand),
        } for si in stock_items]

    critical = _prep(critical_items)
    low = _prep(low_items)
    total_deficit = sum(i["deficit"] for i in critical + low)
    flag = "🚨" if critical else "⚠️"
    subject = f"{flag} Stock bajo — {len(critical) + len(low)} productos ({tenant.name})"
    ctx = _base_ctx(
        tone="red" if critical else "amber",
        subject_line=subject,
        eyebrow="Alerta · Stock bajo",
        hero_title=(f"{len(critical)} productos agotados y {len(low)} bajo el mínimo"
                    if critical else f"{len(low)} productos bajo el mínimo"),
        subtitle=f"{tenant.name} · snapshot del inventario a las {snapshot_at.strftime('%H:%M del %d/%m/%Y')}.",
        critical_count=len(critical),
        low_count=len(low),
        total_deficit=total_deficit,
        total_deficit_formatted=f"{total_deficit} un.",
        critical_items=critical,
        low_items=low,
        cta_text="Ver inventario completo",
        cta_url=f"{APP_URL}/dashboard/inventory/stock",
        secondary_text="Configurar alertas",
        secondary_url=f"{APP_URL}/dashboard/settings?tab=alertas",
    )
    html = render_to_string("emails/low_stock.html", ctx)
    plain = f"Stock bajo: {len(critical)} agotados, {len(low)} bajo mínimo. {APP_URL}/dashboard/inventory/stock"
    return subject, plain, html


def _cantidad(valor, unidad):
    """Una cantidad como la diria una persona: 2.618 ml -> "2,6 L"; 1.500 g ->
    "1,5 kg"; 3 unidades -> "3 un.". Formato chileno (coma decimal, punto de
    miles)."""
    unidad = (unidad or "UN").upper()
    v = float(valor or 0)
    if unidad == "ML" and abs(v) >= 1000:
        v, txt = v / 1000, "L"
    elif unidad == "GR" and abs(v) >= 1000:
        v, txt = v / 1000, "kg"
    else:
        txt = {"ML": "ml", "GR": "g", "KG": "kg", "L": "L"}.get(unidad, unidad.lower())
        if unidad == "UN":
            txt = "unidad" if abs(v) == 1 else "unidades"
    if abs(v) >= 100 or float(v).is_integer():
        num = f"{v:,.0f}"
    else:
        num = f"{v:,.1f}"
    num = num.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{num} {txt}"


def _dias(d, con_en=False):
    """"hoy" / "mañana" / "~3 días" (o "en ~3 días" para "se acaba ...")."""
    if d is None:
        return None
    if d < 1:
        return "hoy"
    if d < 1.5:
        return "mañana"
    return ("en " if con_en else "") + f"~{int(round(d))} días"


def _explicar_alerta(a, dias_a_cubrir=7):
    """Lo que el destinatario necesita para decidir, sin contexto previo:
    cuanto queda, cuanto se usa, por que esta en la lista y cuanto pedir."""
    unidad = a.get("unit") or "UN"
    on_hand = max(float(a.get("on_hand") or 0), 0.0)
    uso = float(a.get("avg_daily") or 0)
    dias = a.get("days_left")
    razon = a.get("reason")

    if on_hand <= 0:
        estado = "Sin stock"
    elif razon == "manual":
        estado = "Bajo tu mínimo"
    elif dias is not None:
        estado = "Se acaba " + _dias(float(dias)) if float(dias) < 1.5 else "Alcanza " + _dias(float(dias))
    else:
        estado = "Stock bajo"

    quedan = ("No queda nada" if on_hand <= 0 else
              f"{'Queda' if _cantidad(on_hand, unidad).endswith(' unidad') else 'Quedan'} {_cantidad(on_hand, unidad)}")
    usa = f"se usan ~{_cantidad(uso, unidad)} por día" if uso > 0 else "casi no rota"
    situacion = f"{quedan} · {usa}"

    if razon == "stockout":
        porque = (f"Se acabó y en las últimas 2 semanas se usaron {_cantidad(uso * 14, unidad)}."
                  if uso > 0 else "Se acabó y tiene un mínimo definido por ti.")
    elif razon == "manual":
        porque = f"Está bajo el mínimo que definiste ({_cantidad(a.get('threshold') or 0, unidad)})."
    elif razon == "forecast":
        porque = f"Según el pronóstico de los próximos días, se acaba {_dias(float(dias), con_en=True)}."
    elif razon == "auto":
        porque = ("Quedan menos días de los que tarda en reponerse." if dias is not None
                  else "Rota poco, pero ya está bajo el mínimo que el sistema calculó para él.")
    else:
        porque = a.get("reason_text", "")

    # Cuanto pedir: lo que se espera usar en los proximos dias segun el
    # pronostico (si hay), si no el promedio; y nunca menos que lo necesario
    # para llegar al minimo que definio el dueño.
    # El mayor de los dos: el pronostico ve los dias fuertes que vienen, pero
    # hoy trae ceros que no son reales (el "cero de hoy" de seasonal_naive: la
    # leche del 29-oct sumaba 3,8 L para 7 dias con dos dias en 0, y sugeria
    # pedir 432 ml). El promedio de uso x dias es el piso.
    necesidad = max(float(a.get("proximos_dias") or 0), uso * dias_a_cubrir)
    if razon == "manual" and a.get("threshold"):
        necesidad = max(necesidad, float(a["threshold"]))
    pedir = max(0.0, necesidad - on_hand)
    if unidad == "UN":
        import math
        pedir = math.ceil(pedir)
    if pedir <= 0:
        sugerencia = ""
    elif razon == "manual" and a.get("threshold") and float(a["threshold"]) >= necesidad - 1e-9:
        sugerencia = f"Para llegar a tu mínimo: pedir ~{_cantidad(pedir, unidad)}"
    else:
        sugerencia = f"Para cubrir {dias_a_cubrir} días: pedir ~{_cantidad(pedir, unidad)}"
    return estado, situacion, porque, sugerencia


def render_low_stock_v2(tenant, critical_alerts, warning_alerts, snapshot_at=None,
                        truncated_count=0, sin_control=None):
    """Correo de stock bajo (29/10/26: reescrito para leerse sin contexto).

    Antes cada fila decia solo "Sin stock / sin stock" o "Predicción: se acaba
    en ~1 día / 1 d": no decia cuanto quedaba, cuanto se usa ni cuanto pedir,
    y avisaba como "critico" productos que se venden sin stock cargado (el Te,
    todos los dias). Ahora cada fila trae estado, situacion (cuanto queda y
    cuanto se usa, con su unidad), el porque en palabras y cuanto pedir para
    7 dias. Lo que se vende sin stock cargado no se avisa (no hay nada que
    reponer); `sin_control` queda en la firma por compatibilidad.
    """
    snapshot_at = snapshot_at or timezone.now()
    sin_control = list(sin_control or [])

    def _prep(alerts):
        out = []
        for a in alerts:
            estado, situacion, porque, sugerencia = _explicar_alerta(a)
            out.append({
                # La plantilla lee `name` (ver tests/test_correo_stock_bajo.py:
                # con `product_name` el HTML salia sin el nombre del producto).
                "name": a["product_name"],
                "product_name": a["product_name"],
                "sku": a["sku"],
                "warehouse": a["warehouse"],
                "estado": estado,
                "situacion": situacion,
                "porque": porque,
                "sugerencia": sugerencia,
            })
        return out

    critical = _prep(critical_alerts)
    low = _prep(warning_alerts)
    total_shown = len(critical) + len(low)
    total_full = total_shown + (truncated_count or 0)

    partes = []
    sin_stock = sum(1 for a in critical_alerts if float(a.get("on_hand") or 0) <= 0)
    if sin_stock:
        partes.append(f"{sin_stock} sin stock")
    otros_criticos = len(critical) - sin_stock
    if otros_criticos:
        partes.append(f"{otros_criticos} se acaba{'n' if otros_criticos != 1 else ''} pronto")
    if low:
        partes.append(f"{len(low)} por reponer")
    resumen = ", ".join(partes) or "sin alertas"
    subject = f"Stock: {resumen} — {tenant.name}"

    base_subtitle = f"{tenant.name} · revisado el {snapshot_at.strftime('%d/%m a las %H:%M')}."
    hero = resumen[:1].upper() + resumen[1:]
    if truncated_count:
        hero += f" (+{truncated_count} más)"

    ctx = _base_ctx(
        pie_corto=True,
        tone="red" if critical else "amber",
        subject_line=subject,
        eyebrow="Alerta · Stock bajo",
        hero_title=hero,
        subtitle=base_subtitle,
        critical_count=len(critical),
        low_count=len(low),
        total_deficit=total_full,
        total_deficit_formatted=f"{total_full} alerta{'s' if total_full != 1 else ''}",
        critical_items=critical,
        low_items=low,
        truncated_count=truncated_count,
        varias_bodegas=len({a.get("warehouse") for a in list(critical_alerts) + list(warning_alerts)}) > 1,
        cta_text=(
            f"Ver los otros {truncated_count} producto{'s' if truncated_count != 1 else ''}"
            if truncated_count else "Ver inventario completo"
        ),
        cta_url=f"{APP_URL}/dashboard/forecast",
        secondary_text="Configurar alertas",
        secondary_url=f"{APP_URL}/dashboard/settings?tab=alertas",
    )
    html = render_to_string("emails/low_stock_v2.html", ctx)

    lines = [f"Pulstock — Stock en {tenant.name}: {resumen}", ""]
    for titulo, items in (("REPONER HOY", critical), ("REPONER PRONTO", low)):
        if not items:
            continue
        lines.append(f"{titulo} ({len(items)}):")
        for it in items:
            lines.append(f"  - {it['name']}: {it['estado']}. {it['situacion']}.")
            if it["sugerencia"]:
                lines.append(f"    {it['sugerencia']}.")
        lines.append("")
    if truncated_count:
        lines.append(f"... y {truncated_count} producto{'s' if truncated_count != 1 else ''} más con menor rotación.")
        lines.append("")
    lines.append(f"Ver detalle completo: {APP_URL}/dashboard/forecast")
    plain = "\n".join(lines)
    return subject, plain, html


# ─────────── Link de pago pendiente (B20) ───────────
def render_payment_link(plan_name, amount_clp, payment_url, access_until=None):
    """El correo que avisa que la renovacion quedo pendiente.

    Era el unico de los once en texto plano. Se paso a plantilla porque desde
    B20 un link de pago ya NO activa el periodo: si este correo no se entiende,
    el cliente se queda sin servicio sin saber por que.
    """
    subject = f"Tu pago de {BRAND} quedó pendiente"
    ctx = _base_ctx(
        tone="amber",
        subject_line=subject,
        eyebrow="Pago pendiente",
        hero_title="Tu renovación quedó pendiente",
        subtitle="No pudimos procesar el cobro automático. Puedes pagarla en un minuto desde el botón de abajo.",
        plan_name=plan_name,
        monto=_fmt_clp(amount_clp),
        payment_url=payment_url,
        access_until=access_until,
        cta_text="Pagar ahora",
        cta_url=payment_url,
    )
    html = render_to_string("emails/payment_link.html", ctx)
    lineas = [
        f"Tu renovación de {plan_name} ({_fmt_clp(amount_clp)}) quedó pendiente.",
        "",
        "Puedes pagarla acá:",
        payment_url,
        "",
        "El pago se acredita al instante.",
        "",
        f"— {BRAND}",
    ]
    plain = chr(10).join(lineas)  # chr(10) = salto de linea
    return subject, plain, html
