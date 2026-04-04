"""
reports/tasks.py
================
Celery tasks for automated report delivery.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper if args and callable(args[0]) is False else wrapper


@shared_task(name="reports.tasks.send_weekly_abc_report", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=300, time_limit=360)
def send_weekly_abc_report(self):
    """
    Runs every Monday 8am. Sends ABC analysis email (HTML) to all active tenant owners.
    """
    from core.models import Tenant, User
    from stores.models import Store
    from reports.services import get_abc_analysis

    now = timezone.now()
    date_to = now.date()
    date_from = date_to - timedelta(days=90)

    sent = 0
    for tenant in Tenant.objects.filter(is_active=True):
        owner = User.objects.filter(
            tenant=tenant, role="owner", is_active=True
        ).values("email", "first_name").first()

        if not owner or not owner["email"]:
            continue

        # Get the first active store for the tenant
        store = Store.objects.filter(tenant=tenant, is_active=True).first()
        if not store:
            continue

        try:
            data = get_abc_analysis(
                t_id=tenant.id, s_id=store.id,
                criterion="revenue",
                date_from=date_from, date_to=date_to,
            )
        except Exception as e:
            logger.warning("ABC analysis failed for tenant %s: %s", tenant.id, e)
            continue

        items = data.get("items", [])
        if not items:
            continue

        # Build summary
        a_items = [i for i in items if i["abc_class"] == "A"]
        b_items = [i for i in items if i["abc_class"] == "B"]
        c_items = [i for i in items if i["abc_class"] == "C"]

        total_revenue = sum(float(i["revenue"]) for i in items)
        total_profit = sum(float(i["profit"]) for i in items)
        avg_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        name = owner.get("first_name") or "Usuario"
        html = _render_abc_html(
            name=name,
            tenant_name=tenant.name,
            a_items=a_items[:10],
            b_items=b_items[:5],
            c_items=c_items[:5],
            total_revenue=total_revenue,
            total_profit=total_profit,
            avg_margin=avg_margin,
            total_products=len(items),
            date_from=date_from,
            date_to=date_to,
        )

        plain = (
            f"Reporte ABC Semanal — {tenant.name}\n\n"
            f"Productos A: {len(a_items)}, B: {len(b_items)}, C: {len(c_items)}\n"
            f"Revenue total: ${total_revenue:,.0f} CLP\n"
            f"Ver detalle en https://app.inventario.pro/dashboard/reports\n"
        )

        send_mail(
            subject=f"Reporte ABC Semanal — {tenant.name}",
            message=plain,
            html_message=html,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@inventario.pro"),
            recipient_list=[owner["email"]],
            fail_silently=False,
        )
        sent += 1
        logger.info("ABC report sent to %s (tenant %s)", owner["email"], tenant.id)

    logger.info("send_weekly_abc_report: %d emails sent", sent)
    return {"sent": sent}


def _render_abc_html(*, name, tenant_name, a_items, b_items, c_items,
                     total_revenue, total_profit, avg_margin,
                     total_products, date_from, date_to):
    """Render inline-styled HTML email for ABC analysis."""

    def _product_rows(items, bg_color):
        rows = ""
        for i in items:
            margin = i.get("margin_pct", "0")
            rows += f"""
            <tr style="border-bottom:1px solid #E4E4E7;">
                <td style="padding:8px 12px;font-size:13px;">{i['product_name']}</td>
                <td style="padding:8px 12px;font-size:13px;font-family:monospace;">{i['sku']}</td>
                <td style="padding:8px 12px;font-size:13px;text-align:right;">${float(i['revenue']):,.0f}</td>
                <td style="padding:8px 12px;font-size:13px;text-align:right;">{margin}%</td>
                <td style="padding:8px 6px;text-align:center;">
                    <span style="display:inline-block;padding:2px 8px;border-radius:10px;
                                 font-size:11px;font-weight:700;background:{bg_color};
                                 color:#fff;">{i['abc_class']}</span>
                </td>
            </tr>"""
        return rows

    a_rows = _product_rows(a_items, "#16A34A")
    b_rows = _product_rows(b_items, "#F59E0B")
    c_rows = _product_rows(c_items, "#94A3B8")

    return f"""
    <div style="font-family:'DM Sans',Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;color:#18181B;">
        <!-- Header -->
        <div style="background:#4F46E5;padding:24px 28px;border-radius:12px 12px 0 0;">
            <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">Reporte ABC Semanal</h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">
                {tenant_name} · {date_from.strftime('%d/%m/%Y')} al {date_to.strftime('%d/%m/%Y')}
            </p>
        </div>

        <div style="background:#fff;border:1px solid #E4E4E7;border-top:none;padding:24px 28px;border-radius:0 0 12px 12px;">
            <p style="margin:0 0 20px;font-size:14px;">Hola {name},</p>

            <!-- KPIs -->
            <div style="display:flex;gap:12px;margin-bottom:24px;">
                <div style="flex:1;background:#F7F7F8;border:1px solid #E4E4E7;border-radius:8px;padding:14px 16px;text-align:center;">
                    <div style="font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;letter-spacing:0.05em;">Revenue</div>
                    <div style="font-size:22px;font-weight:800;color:#18181B;margin-top:4px;">${total_revenue:,.0f}</div>
                </div>
                <div style="flex:1;background:#F7F7F8;border:1px solid #E4E4E7;border-radius:8px;padding:14px 16px;text-align:center;">
                    <div style="font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;letter-spacing:0.05em;">Utilidad</div>
                    <div style="font-size:22px;font-weight:800;color:#16A34A;margin-top:4px;">${total_profit:,.0f}</div>
                </div>
                <div style="flex:1;background:#F7F7F8;border:1px solid #E4E4E7;border-radius:8px;padding:14px 16px;text-align:center;">
                    <div style="font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;letter-spacing:0.05em;">Margen</div>
                    <div style="font-size:22px;font-weight:800;color:#4F46E5;margin-top:4px;">{avg_margin:.1f}%</div>
                </div>
            </div>

            <!-- Distribution -->
            <div style="margin-bottom:24px;font-size:13px;color:#52525B;">
                <strong>{total_products}</strong> productos analizados:
                <span style="color:#16A34A;font-weight:700;">{len(a_items)} A</span> (80% revenue) ·
                <span style="color:#F59E0B;font-weight:700;">{len(b_items)} B</span> (15%) ·
                <span style="color:#94A3B8;font-weight:700;">{len(c_items)} C</span> (5%)
            </div>

            <!-- Top A products -->
            <h3 style="margin:0 0 10px;font-size:14px;font-weight:700;">Top Productos A (mayor revenue)</h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <thead>
                    <tr style="background:#F7F7F8;border-bottom:2px solid #E4E4E7;">
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;text-align:left;">Producto</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;text-align:left;">SKU</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;text-align:right;">Revenue</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;text-align:right;">Margen</th>
                        <th style="padding:8px 6px;font-size:10px;font-weight:700;color:#71717A;text-transform:uppercase;text-align:center;">Clase</th>
                    </tr>
                </thead>
                <tbody>{a_rows}</tbody>
            </table>

            {"<h3 style='margin:0 0 10px;font-size:14px;font-weight:700;'>Productos B (oportunidad de crecimiento)</h3><table style='width:100%;border-collapse:collapse;margin-bottom:20px;'><tbody>" + b_rows + "</tbody></table>" if b_rows else ""}

            {"<h3 style='margin:0 0 10px;font-size:14px;font-weight:700;color:#94A3B8;'>Productos C (revisar rotación)</h3><table style='width:100%;border-collapse:collapse;margin-bottom:20px;'><tbody>" + c_rows + "</tbody></table>" if c_rows else ""}

            <!-- CTA -->
            <div style="text-align:center;margin:24px 0 12px;">
                <a href="https://app.inventario.pro/dashboard/reports" style="display:inline-block;padding:10px 28px;background:#4F46E5;color:#fff;font-size:13px;font-weight:700;text-decoration:none;border-radius:6px;">
                    Ver reporte completo
                </a>
            </div>

            <p style="margin:20px 0 0;font-size:12px;color:#A1A1AA;text-align:center;">
                Este email se envía cada lunes. Puedes desactivarlo en Configuración.
            </p>
        </div>
    </div>
    """
