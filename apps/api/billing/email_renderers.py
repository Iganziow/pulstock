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
SETTINGS_URL = f"{APP_URL}/dashboard/settings?tab=suscripcion"
BRAND = "Pulstock"
SUPPORT_EMAIL = "soporte@pulstock.cl"
LOGO_URL = "https://pulstock.cl/email-logo.png?v=20260424"

TONES = {
    "indigo": {"eyebrow_bg": "#EEF2FF", "eyebrow_fg": "#4F46E5",
               "cta_bg": "#4F46E5", "cta_grad1": "#4F46E5", "cta_grad2": "#7C3AED"},
    "green":  {"eyebrow_bg": "#ECFDF5", "eyebrow_fg": "#16A34A",
               "cta_bg": "#16A34A", "cta_grad1": "#16A34A", "cta_grad2": "#16A34A"},
    "red":    {"eyebrow_bg": "#FEF2F2", "eyebrow_fg": "#DC2626",
               "cta_bg": "#DC2626", "cta_grad1": "#DC2626", "cta_grad2": "#DC2626"},
    "amber":  {"eyebrow_bg": "#FFFBEB", "eyebrow_fg": "#D97706",
               "cta_bg": "#D97706", "cta_grad1": "#D97706", "cta_grad2": "#D97706"},
    "black":  {"eyebrow_bg": "#E4E4E7", "eyebrow_fg": "#18181B",
               "cta_bg": "#18181B", "cta_grad1": "#18181B", "cta_grad2": "#3F3F46"},
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
def render_renewal_reminder(sub, days_left, payment_method="Visa ···· 4829"):
    plan = sub.plan
    plan.price_formatted = _fmt_clp(plan.price_clp)
    end = sub.current_period_end
    next_end = end + timedelta(days=30) if end else None
    period_range = f"{end.strftime('%d/%m')} → {next_end.strftime('%d/%m/%Y')}" if end and next_end else "—"
    subject = f"Tu suscripción se renueva en {days_left} días — {BRAND}"
    ctx = _base_ctx(
        tone="indigo",
        subject_line=subject,
        eyebrow=f"Renovación · En {days_left} días",
        hero_title=f"Renovaremos tu suscripción el {end.strftime('%d de %B').lower() if end else 'próximamente'}",
        subtitle="No tienes que hacer nada: cobraremos automáticamente tu método de pago registrado.",
        plan=plan, user=sub.tenant,
        current_period_end=end,
        payment_method=payment_method,
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
def render_payment_failed(sub, invoice_number, failure_reason="fondos insuficientes",
                          payment_method="Visa ···· 4829", access_until=None):
    plan = sub.plan
    plan.price_formatted = _fmt_clp(plan.price_clp)
    access_until = access_until or (timezone.now() + timedelta(days=3))
    subject = f"⚠️ No pudimos procesar tu pago — {BRAND}"
    ctx = _base_ctx(
        tone="red",
        subject_line=subject,
        eyebrow=f"Pago · Intento {sub.payment_retry_count} de 3",
        hero_title="No pudimos procesar tu pago",
        subtitle=f"Tu tarjeta fue rechazada por el banco emisor. Actualiza tu método de pago antes del {access_until.strftime('%d de %B').lower()} para mantener tu acceso.",
        payment_failed_title=f"{payment_method} fue rechazada",
        payment_failed_body=f"Motivo informado: <em>{failure_reason}</em>. Volveremos a intentar el cobro en 48 horas. Si falla 3 veces, tu cuenta se suspenderá temporalmente.",
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
                             payment_method="Visa ···· 4829", charged_at=None):
    amount = amount or sub.plan.price_clp
    amount_formatted = _fmt_clp(amount)
    charged_at = charged_at or timezone.now()
    subject = f"✅ Pago procesado — {BRAND}"
    ctx = _base_ctx(
        tone="green",
        subject_line=subject,
        eyebrow="Pago · Procesado",
        hero_title="¡Listo! Procesamos tu pago correctamente",
        subtitle="Tu suscripción sigue activa y tienes acceso completo a todas las funciones.",
        recovered_title=f"Cobro exitoso · {amount_formatted}",
        recovered_body=f"Cargado a <span style='font-family:JetBrains Mono,monospace;'>{payment_method}</span> el {charged_at.strftime('%d/%m/%Y a las %H:%M')}.",
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
def render_trial_converted(sub, payment_method="Visa ···· 4829"):
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
        payment_method=payment_method,
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
def render_trial_expired(sub, products_count=0, products_limit=100):
    previous_plan_name = sub.plan.name
    free_features_html = (
        "<div style='display:block;margin-top:6px;'>"
        "• Hasta 100 productos &nbsp; • 1 local, 1 bodega<br>"
        "• 1 usuario &nbsp; • Reportes básicos"
        "</div>"
    )
    subject = f"Tu prueba terminó — {BRAND}"
    ctx = _base_ctx(
        tone="amber",
        subject_line=subject,
        eyebrow="Prueba · Finalizada",
        hero_title="Tu prueba terminó — ahora estás en el plan Gratuito",
        subtitle="No pudimos procesar el pago. Tu cuenta sigue activa, pero con algunos límites.",
        free_plan_features_html=free_features_html,
        previous_plan_name=previous_plan_name,
        products_usage=f"{products_count} / {products_limit} activos",
        cta_text=f"Volver a {previous_plan_name}",
        cta_url=SETTINGS_URL,
        secondary_text="Continuar en plan gratuito",
        secondary_url=f"{APP_URL}/dashboard",
    )
    html = render_to_string("emails/trial_expired.html", ctx)
    plain = f"Tu prueba terminó. Ahora en plan Gratuito. Volver a {previous_plan_name}: {SETTINGS_URL}"
    return subject, plain, html


# ─────────── 09 ABC weekly ───────────
def render_abc_weekly(tenant, date_from, date_to, items_a, items_b, items_c,
                      total_revenue, total_profit):
    margin_pct = (total_profit / total_revenue * 100) if total_revenue else 0
    products_count = len(items_a) + len(items_b) + len(items_c)

    def _fmt_short(n):
        if n >= 1_000_000:
            return f"${n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"${n/1_000:.0f}k"
        return f"${n:.0f}"

    def _prep(items, cls):
        return [{
            "name": i["product_name"],
            "sku": i.get("sku", "—"),
            "units": f"{int(i.get('units', 0)):,}".replace(",", "."),
            "revenue_formatted": _fmt_short(float(i["revenue"])),
            "margin_pct": f"{float(i.get('margin_pct', 0)):.0f}",
            "cls": cls,
        } for i in items]

    subject = f"Reporte ABC Semanal — {tenant.name}"
    ctx = _base_ctx(
        tone="indigo",
        subject_line=subject,
        eyebrow="Reporte · ABC semanal",
        hero_title="Tus productos estrella de los últimos 90 días",
        subtitle=f"{tenant.name} · {date_from.strftime('%d %b')} → {date_to.strftime('%d %b %Y')}. {len(items_a)} productos A concentran el 80% de tus ingresos.",
        kpis={
            "revenue_formatted": _fmt_short(total_revenue),
            "revenue_delta": "",
            "profit_formatted": _fmt_short(total_profit),
            "margin_pct": f"{margin_pct:.0f}",
            "products_count": f"{products_count}",
        },
        class_counts={"a_count": len(items_a), "b_count": len(items_b), "c_count": len(items_c)},
        class_bars={"a_pct": 80, "b_pct": 15, "c_pct": 5},
        items_a=_prep(items_a[:5], "A"),
        items_b=_prep(items_b[:3], "B"),
        cta_text="Ver reporte completo",
        cta_url=f"{APP_URL}/dashboard/reports",
        secondary_text="Ver histórico de reportes",
        secondary_url=f"{APP_URL}/dashboard/reports",
    )
    html = render_to_string("emails/abc_weekly.html", ctx)
    plain = f"Reporte ABC — {tenant.name}. Revenue: {_fmt_short(total_revenue)}. Ver: {APP_URL}/dashboard/reports"
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
