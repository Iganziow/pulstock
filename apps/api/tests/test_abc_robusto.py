# -*- coding: utf-8 -*-
"""
tests/test_abc_robusto.py — el reporte ABC (correo del lunes, pagina y PDF)
no muestra margenes falsos ni numeros sin unidad.

Lo que se vio en el correo del 2-nov-2026 con los datos de Marbrava:
  · "Jugo natural mango · margen 100%" y "Alfajor phaway · -8%": las ventas
    se registraron antes de que el producto tuviera costo cargado (line_cost
    0) o con la receta a medias (un jugo a $11 el vaso).
  · "Chocolate Premium · 3.303 unid." — se vende por gramo: son 3,3 kg.
  · "04 Aug → 02 Nov", "Revenue", "$6.6M": ingles y cifras abreviadas.
  · Las barras A/B/C decian 80/15/5 fijo, no el reparto real.
  · Era "semanal" pero no contaba nada de la semana.
"""
import datetime as dt
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from catalog.models import Product
from inventory.models import StockItem
from reports.services import get_abc_analysis
from sales.models import Sale, SaleLine

D = Decimal


def _venta(tenant, store, warehouse, owner, product, qty, precio, costo):
    qty, precio, costo = D(str(qty)), D(str(precio)), D(str(costo))
    total, costo_total = qty * precio, qty * costo
    s = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        status=Sale.STATUS_COMPLETED, sale_type=Sale.SALE_TYPE_VENTA,
        subtotal=total, total=total, total_cost=costo_total, gross_profit=total - costo_total,
    )
    SaleLine.objects.create(
        sale=s, tenant=tenant, product=product, qty=qty, unit_price=precio, line_total=total,
        unit_cost_snapshot=costo, line_cost=costo_total, line_gross_profit=total - costo_total,
    )
    return s


def _producto(tenant, warehouse, nombre, precio, costo_hoy, unit="UN"):
    p = Product.objects.create(tenant=tenant, name=nombre, price=D(str(precio)), unit=unit, is_active=True)
    if costo_hoy is not None:
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                                 on_hand=D("10"), avg_cost=D(str(costo_hoy)))
    return p


def _fila(data, producto):
    return next(r for r in data["results"] if r["product_id"] == producto.id)


@pytest.mark.django_db
class TestMargenConCostoIncompleto:
    def test_con_costo_normal_el_margen_es_el_registrado(self, tenant, store, warehouse, owner):
        p = _producto(tenant, warehouse, "Americano", 2800, 500)
        _venta(tenant, store, warehouse, owner, p, 10, 2800, 500)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["cost_complete"] is True and f["cost_note"] == ""
        assert f["margin_pct"] == "82.1"
        assert f["unit"] == "UN"

    def test_vendido_sin_costo_no_dice_100_por_ciento(self, tenant, store, warehouse, owner):
        """El jugo de mango: 12 ventas con line_cost 0, hoy cuesta $1.000."""
        p = _producto(tenant, warehouse, "Jugo natural mango", 3800, 1000)
        _venta(tenant, store, warehouse, owner, p, 12, 3800, 0)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["margin_pct"] is None, "un margen sobre costo cero es falso"
        assert f["cost_complete"] is False
        assert f["cost_note"] == "sin costo registrado"
        # Estimado con el costo de hoy: (3.800 - 1.000) / 3.800
        assert f["margin_pct_at_current_cost"] == "73.7"

    def test_sin_costo_registrado_ni_actual_no_hay_estimacion(self, tenant, store, warehouse, owner):
        p = _producto(tenant, warehouse, "Caja de empolvados", 5600, None)
        _venta(tenant, store, warehouse, owner, p, 2, 5600, 0)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["margin_pct"] is None
        assert f["margin_pct_at_current_cost"] is None

    def test_algunas_ventas_sin_costo_lo_dicen_con_numeros(self, tenant, store, warehouse, owner):
        p = _producto(tenant, warehouse, "Chai latte", 4000, 1200)
        _venta(tenant, store, warehouse, owner, p, 1, 4000, 1200)
        _venta(tenant, store, warehouse, owner, p, 1, 4000, 1200)
        _venta(tenant, store, warehouse, owner, p, 1, 4000, 0)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["margin_pct"] is None
        assert f["cost_note"] == "1 de 3 ventas sin costo registrado"

    def test_costo_registrado_muy_por_debajo_del_actual(self, tenant, store, warehouse, owner):
        """El jugo de arandano se registro a $11 el vaso (solo un ingrediente
        costeado); hoy cuesta $1.000. Ese 99,7% de margen no existe."""
        p = _producto(tenant, warehouse, "Jugo natural arandano", 3800, 1000)
        _venta(tenant, store, warehouse, owner, p, 13, 3800, 11)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["margin_pct"] is None
        assert "muy por debajo del actual" in f["cost_note"]
        assert "$11" in f["cost_note"] and "$1.000" in f["cost_note"]
        assert f["margin_pct_at_current_cost"] == "73.7"

    def test_un_alza_normal_de_costo_no_se_marca(self, tenant, store, warehouse, owner):
        p = _producto(tenant, warehouse, "Queso", 1000, 650)
        _venta(tenant, store, warehouse, owner, p, 5, 1000, 500)     # subio 30%: normal
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["cost_complete"] is True and f["margin_pct"] == "50.0"

    def test_el_resumen_dice_cuanta_venta_tiene_costo_incompleto(self, tenant, store, warehouse, owner):
        ok = _producto(tenant, warehouse, "Americano", 2800, 500)
        _venta(tenant, store, warehouse, owner, ok, 10, 2800, 500)
        malo = _producto(tenant, warehouse, "Jugo natural mango", 3800, 1000)
        _venta(tenant, store, warehouse, owner, malo, 12, 3800, 0)
        meta = get_abc_analysis(tenant.id, store.id)["meta"]
        assert meta["cost_incomplete_products"] == 1
        assert D(meta["cost_incomplete_revenue"]) == D("45600")

    def test_la_unidad_viaja_con_la_fila(self, tenant, store, warehouse, owner):
        p = _producto(tenant, warehouse, "Chocolate Premium", 90, 50, unit="GR")
        _venta(tenant, store, warehouse, owner, p, 3303, 90, 50)
        f = _fila(get_abc_analysis(tenant.id, store.id), p)
        assert f["unit"] == "GR" and D(f["qty"]) == D("3303")


def _item(nombre, revenue, qty, margen, unit="UN", **extra):
    base = {"product_name": nombre, "sku": "S", "revenue": str(revenue), "qty": str(qty),
            "profit": "0", "margin_pct": margen, "unit": unit, "cost_complete": margen is not None,
            "cost_note": "", "margin_pct_at_current_cost": None, "abc_class": "A"}
    base.update(extra)
    return base


@pytest.mark.django_db
class TestElCorreoSeLeeEnChileno:
    def _render(self, tenant, **kw):
        from billing.email_renderers import render_abc_weekly
        items_a = kw.pop("items_a", [_item("Americano", 602000, 215, "82.9")])
        return render_abc_weekly(
            tenant, dt.date(2026, 8, 4), dt.date(2026, 11, 1), items_a,
            kw.pop("items_b", []), kw.pop("items_c", []),
            total_revenue=kw.pop("total_revenue", 6624020), total_profit=kw.pop("total_profit", 4616205), **kw)

    def test_fechas_y_rotulos_en_espanol(self, tenant):
        asunto, plano, html = self._render(tenant)
        assert "4 ago al 1 nov 2026" in html
        for ingles in ("Aug", "Nov 2026.", "Revenue", "$6.6M", "$602k"):
            assert ingles not in html and ingles not in plano, ingles
        assert "$6.624.020" in html and "$602.000" in html
        assert "semana del 26 oct" in asunto

    def test_los_gramos_se_leen_en_kilos(self, tenant):
        _a, plano, html = self._render(tenant, items_a=[_item("Chocolate Premium", 297270, 3303, "44.4", unit="GR")])
        assert "3,3 kg" in html and "3,3 kg" in plano
        assert "3.303" not in html

    def test_margen_estimado_con_aviso_y_sin_costo_con_raya(self, tenant):
        items = [
            _item("Americano", 602000, 215, "82.9"),
            _item("Jugo natural mango", 45600, 12, None, cost_note="sin costo registrado",
                  margin_pct_at_current_cost="73.7"),
            _item("Caja de empolvados", 11200, 2, None, cost_note="sin costo registrado"),
        ]
        _a, plano, html = self._render(tenant, items_a=items)
        assert "83%</td>" in html and "≈74%</td>" in html and "—</td>" in html
        assert "100%</td>" not in html, "el jugo sin costo no puede salir con 100% de margen"
        assert "sin costo registrado" in html
        assert "margen estimado con el costo de hoy" in html and "estimado" in plano

    def test_sin_margenes_estimados_no_hay_nota(self, tenant):
        _a, plano, html = self._render(tenant)
        assert "estimado" not in html and "estimado" not in plano

    def test_las_barras_usan_el_reparto_real(self, tenant):
        a = [_item("A1", 7200, 1, "50.0")]
        b = [_item("B1", 2000, 1, "50.0")]
        c = [_item("C1", 800, 1, "50.0")]
        _a, _p, html = self._render(tenant, items_a=a, items_b=b, items_c=c, total_revenue=10000, total_profit=5000)
        assert "1 A · 72%" in html and "1 B · 20%" in html and "1 C · 8%" in html
        assert 'width="72%"' in html
        assert "concentran el 72% de los ingresos" in html

    def test_la_semana_que_cerro_va_arriba(self, tenant):
        semana = {"actual": {"desde": dt.date(2026, 10, 26), "hasta": dt.date(2026, 11, 1), "total": D("343350"), "boletas": 38},
                  "anterior": {"desde": dt.date(2026, 10, 19), "hasta": dt.date(2026, 10, 25), "total": D("520000"), "boletas": 61},
                  "variacion_pct": -34.0}
        _a, plano, html = self._render(tenant, semana=semana)
        assert "Semana del 26 oct al 1 nov" in html
        assert "$343.350" in html and "38 boletas" in html
        assert "−34% contra la semana anterior ($520.000)" in html
        assert "Semana del 26 oct al 1 nov: $343.350 en 38 boletas" in plano

    def test_la_utilidad_avisa_si_hay_costo_incompleto(self, tenant):
        meta = {"cost_incomplete_products": 22, "cost_incomplete_revenue": "170770"}
        _a, plano, html = self._render(tenant, meta=meta)
        assert "22 productos ($170.770 de venta) se vendieron sin costo cargado" in html
        assert "la utilidad real es menor" in plano

    def test_sin_emojis(self, tenant):
        asunto, plano, html = self._render(tenant)
        for e in ("🚨", "⚠", "💡", "📊", "⭐", "🥇"):
            assert e not in asunto and e not in html and e not in plano


@pytest.mark.django_db
class TestLaTareaDelLunes:
    def test_resumen_semana_compara_con_la_anterior(self, tenant, store, warehouse, owner):
        from reports.tasks import resumen_semana
        p = _producto(tenant, warehouse, "Americano", 2800, 500)
        domingo = timezone.localdate()
        for dias, n in ((2, 3), (9, 6)):          # esta semana 3 boletas, la anterior 6
            for _ in range(n):
                s = _venta(tenant, store, warehouse, owner, p, 1, 2800, 500)
                Sale.objects.filter(id=s.id).update(created_at=timezone.now() - dt.timedelta(days=dias))
        r = resumen_semana(tenant.id, store.id, domingo)
        assert r["actual"]["boletas"] == 3 and r["actual"]["total"] == D("8400")
        assert r["anterior"]["boletas"] == 6
        assert r["variacion_pct"] == pytest.approx(-50.0)

    def test_la_ventana_cierra_el_domingo_y_son_90_dias(self, tenant, store, warehouse, owner):
        """El cron corre el lunes 8:00: el lunes a medias no entra, y el
        correo no dice "ultimos 90 dias" sobre 91."""
        owner.email = "mario@marbrava.cl"; owner.save(update_fields=["email"])
        p = _producto(tenant, warehouse, "Americano", 2800, 500)
        _venta(tenant, store, warehouse, owner, p, 10, 2800, 500)
        lunes = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)
        from reports import tasks
        with mock.patch("django.utils.timezone.now", return_value=lunes), \
             mock.patch("billing.email_renderers.render_abc_weekly",
                        return_value=("a", "p", "<p>h</p>")) as render:
            Sale.objects.update(created_at=lunes - dt.timedelta(days=3))
            mail.outbox.clear()
            tasks.send_weekly_abc_report()
        assert render.called, "con una venta en la ventana el correo sale"
        kw = render.call_args.kwargs
        assert kw["date_to"] == dt.date(2026, 11, 1)
        assert kw["date_from"] == dt.date(2026, 8, 4)
        assert (kw["date_to"] - kw["date_from"]).days + 1 == 90
        assert kw["semana"]["actual"]["hasta"] == dt.date(2026, 11, 1)
        assert "cost_incomplete_products" in kw["meta"]
        assert len(mail.outbox) == 1
