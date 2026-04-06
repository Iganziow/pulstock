"""
inventory/tasks.py
==================
Celery tasks for inventory alerts.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F, Q

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper if args and callable(args[0]) is False else wrapper


@shared_task(name="inventory.tasks.send_low_stock_alerts", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=300, time_limit=360)
def send_low_stock_alerts(self):
    """
    Runs daily at 7:30am. Sends email to tenant owners when products are
    below their min_stock threshold.
    """
    from core.models import Tenant, User, AlertPreference
    from inventory.models import StockItem

    sent = 0
    for tenant in Tenant.objects.filter(is_active=True):
        # Check owner preferences
        owner = User.objects.filter(
            tenant=tenant, role="owner", is_active=True
        ).first()
        if not owner or not owner.email:
            continue

        # Check if stock_bajo alert is enabled
        try:
            prefs = AlertPreference.objects.get(user=owner)
            if not prefs.stock_bajo:
                continue
        except AlertPreference.DoesNotExist:
            pass  # No prefs = defaults (stock_bajo=True)

        # Query low stock items: on_hand < product.min_stock where min_stock > 0
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
            continue

        # Critical: on_hand = 0
        critical = [i for i in low_items if i.on_hand <= 0]
        low = [i for i in low_items if i.on_hand > 0]

        html = _render_low_stock_email(
            name=owner.first_name or "Usuario",
            tenant_name=tenant.name,
            critical_items=critical,
            low_items=low,
        )

        plain = (
            f"Alerta de Stock Bajo — {tenant.name}\n\n"
            f"{len(critical)} productos agotados, {len(low)} con stock bajo.\n"
            f"Ver detalle en https://app.pulstock.cl/dashboard/inventory/stock\n"
        )

        try:
            send_mail(
                subject=f"{'🚨' if critical else '⚠️'} Stock bajo — {len(low_items)} productos ({tenant.name})",
                message=plain,
                html_message=html,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "Pulstock <noreply@pulstock.cl>"),
                recipient_list=[owner.email],
                fail_silently=False,
            )
            sent += 1
            logger.info("Low stock alert sent to %s (tenant %s, %d items)",
                        owner.email, tenant.id, len(low_items))
        except Exception as e:
            logger.error("Failed to send low stock alert to %s: %s", owner.email, e)
            raise

    logger.info("send_low_stock_alerts: %d emails sent", sent)
    return {"sent": sent}


def _render_low_stock_email(*, name, tenant_name, critical_items, low_items):
    """Render inline-styled HTML email for low stock alert."""

    def _rows(items, is_critical):
        rows = ""
        for si in items:
            p = si.product
            on_hand = float(si.on_hand)
            min_stock = float(p.min_stock)
            deficit = min_stock - on_hand
            bg = "#FEF2F2" if is_critical else "#FFFBEB"
            status = "AGOTADO" if on_hand <= 0 else f"{on_hand:.0f}"
            status_color = "#DC2626" if is_critical else "#D97706"

            rows += f"""
            <tr style="border-bottom:1px solid #E4E4E7;">
                <td style="padding:8px 12px;font-size:13px;font-weight:600;">{p.name}</td>
                <td style="padding:8px 12px;font-size:12px;font-family:monospace;color:#71717A;">{p.sku or '—'}</td>
                <td style="padding:8px 12px;font-size:12px;">{si.warehouse.name if si.warehouse else '—'}</td>
                <td style="padding:8px 12px;text-align:right;">
                    <span style="padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;
                                 background:{bg};color:{status_color};">{status}</span>
                </td>
                <td style="padding:8px 12px;font-size:12px;text-align:right;">{min_stock:.0f}</td>
                <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:700;color:#4F46E5;">+{deficit:.0f}</td>
            </tr>"""
        return rows

    critical_rows = _rows(critical_items, True)
    low_rows = _rows(low_items, False)
    total = len(critical_items) + len(low_items)

    return f"""
    <div style="font-family:'DM Sans',Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;color:#18181B;">
        <div style="background:{'#DC2626' if critical_items else '#D97706'};padding:24px 28px;border-radius:12px 12px 0 0;">
            <h1 style="margin:0;color:#fff;font-size:20px;font-weight:800;">
                {'🚨' if critical_items else '⚠️'} Alerta de Stock Bajo
            </h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">
                {tenant_name} · {total} producto{'s' if total != 1 else ''} necesita{'n' if total != 1 else ''} reposición
            </p>
        </div>

        <div style="background:#fff;border:1px solid #E4E4E7;border-top:none;padding:24px 28px;border-radius:0 0 12px 12px;">
            <p style="margin:0 0 20px;font-size:14px;">Hola {name},</p>

            {f'''
            <h3 style="margin:0 0 10px;font-size:14px;font-weight:700;color:#DC2626;">
                Productos agotados ({len(critical_items)})
            </h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <thead>
                    <tr style="background:#FEF2F2;border-bottom:2px solid #FECACA;">
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:left;">Producto</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:left;">SKU</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:left;">Bodega</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:right;">Stock</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:right;">Mínimo</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#DC2626;text-transform:uppercase;text-align:right;">Pedir</th>
                    </tr>
                </thead>
                <tbody>{critical_rows}</tbody>
            </table>
            ''' if critical_items else ''}

            {f'''
            <h3 style="margin:0 0 10px;font-size:14px;font-weight:700;color:#D97706;">
                Stock bajo ({len(low_items)})
            </h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <thead>
                    <tr style="background:#FFFBEB;border-bottom:2px solid #FDE68A;">
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:left;">Producto</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:left;">SKU</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:left;">Bodega</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:right;">Stock</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:right;">Mínimo</th>
                        <th style="padding:8px 12px;font-size:10px;font-weight:700;color:#D97706;text-transform:uppercase;text-align:right;">Pedir</th>
                    </tr>
                </thead>
                <tbody>{low_rows}</tbody>
            </table>
            ''' if low_items else ''}

            <div style="text-align:center;margin:24px 0 12px;">
                <a href="https://app.pulstock.cl/dashboard/inventory/stock" style="display:inline-block;padding:10px 28px;background:#4F46E5;color:#fff;font-size:13px;font-weight:700;text-decoration:none;border-radius:6px;">
                    Ver inventario completo
                </a>
            </div>

            <p style="margin:20px 0 0;font-size:12px;color:#A1A1AA;text-align:center;">
                Puedes desactivar estas alertas en Configuración → Alertas.
            </p>
        </div>
    </div>
    """
