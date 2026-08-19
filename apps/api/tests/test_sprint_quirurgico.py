"""
tests/test_sprint_quirurgico.py — B1, B3, B7, B11 de la auditoría de julio.

Los cuatro comparten la misma naturaleza: el dato existe, la UI lo pide, y el
backend lo tira a la basura en silencio. Ninguno lanzaba error, así que nadie
se enteraba.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Unit
from catalog.unit_conversion import convert_qty
from core.models import AuditEntry
from purchases.models import Purchase
from sales.models import Sale, SalePayment

D = Decimal


def _count(payload):
    """La lista puede venir paginada o como array plano."""
    if isinstance(payload, dict) and "count" in payload:
        return payload["count"]
    if isinstance(payload, dict) and "results" in payload:
        return len(payload["results"])
    return len(payload)


# ── B1: los filtros de fecha de compras no filtraban nada ───────────────

@pytest.mark.django_db
class TestB1FiltroFechasCompras:
    def _compra(self, tenant, store, warehouse, owner, dias_atras):
        po = Purchase.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner, supplier_name="Prov", status="POSTED",
        )
        # created_at tiene default=now; hay que pisarlo con UPDATE.
        Purchase.objects.filter(pk=po.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=dias_atras)
        )
        return po

    def test_date_from_filtra(self, api_client, tenant, store, warehouse, owner):
        """El frontend manda date_from/date_to (los botones Hoy/7d/30d). Antes
        el backend solo leía from/to, así que los botones no hacían nada."""
        self._compra(tenant, store, warehouse, owner, dias_atras=1)
        self._compra(tenant, store, warehouse, owner, dias_atras=40)

        desde = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        r = api_client.get("/api/purchases/?date_from=" + desde)
        assert r.status_code == 200, r.content
        assert _count(r.json()) == 1

    def test_from_sigue_funcionando(self, api_client, tenant, store, warehouse, owner):
        """Compatibilidad: el nombre viejo no se rompe."""
        self._compra(tenant, store, warehouse, owner, dias_atras=1)
        self._compra(tenant, store, warehouse, owner, dias_atras=40)
        desde = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        r = api_client.get("/api/purchases/?from=" + desde)
        assert _count(r.json()) == 1

    def test_sin_filtro_devuelve_todo(self, api_client, tenant, store, warehouse, owner):
        self._compra(tenant, store, warehouse, owner, dias_atras=1)
        self._compra(tenant, store, warehouse, owner, dias_atras=40)
        r = api_client.get("/api/purchases/")
        assert _count(r.json()) == 2


# ── B3: el motivo de anulación se descartaba ────────────────────────────

def _venta(tenant, store, warehouse, owner, total="10000"):
    return Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        subtotal=D(total), total=D(total), status="COMPLETED", sale_type="VENTA",
    )


@pytest.mark.django_db
class TestB3MotivoAnulacion:
    def test_el_motivo_se_guarda(self, api_client, tenant, store, warehouse, owner):
        """El frontend lo exige y lo manda desde siempre; el backend no lo
        leía. Una venta anulada no decía por qué."""
        v = _venta(tenant, store, warehouse, owner)
        r = api_client.post(
            "/api/sales/sales/%d/void/" % v.id,
            {"reason": "cliente se arrepintio"}, format="json",
        )
        assert r.status_code == 200, r.content
        v.refresh_from_db()
        assert v.void_reason == "cliente se arrepintio"

    def test_el_motivo_queda_en_la_auditoria(self, api_client, tenant, store, warehouse, owner):
        v = _venta(tenant, store, warehouse, owner)
        api_client.post(
            "/api/sales/sales/%d/void/" % v.id,
            {"reason": "error de digitacion"}, format="json",
        )
        a = AuditEntry.objects.filter(action="sale_void", entity_id=v.id).first()
        assert a is not None
        assert a.detail.get("reason") == "error de digitacion"

    def test_el_detalle_lo_expone(self, api_client, tenant, store, warehouse, owner):
        """U7: la ficha de la venta tiene que poder mostrarlo."""
        v = _venta(tenant, store, warehouse, owner)
        api_client.post(
            "/api/sales/sales/%d/void/" % v.id,
            {"reason": "producto en mal estado"}, format="json",
        )
        r = api_client.get("/api/sales/sales/%d/" % v.id)
        assert r.json()["void_reason"] == "producto en mal estado"

    def test_sin_motivo_no_rompe(self, api_client, tenant, store, warehouse, owner):
        """Integraciones viejas que no mandan reason siguen pudiendo anular."""
        v = _venta(tenant, store, warehouse, owner)
        r = api_client.post("/api/sales/sales/%d/void/" % v.id, {}, format="json")
        assert r.status_code == 200, r.content
        v.refresh_from_db()
        assert v.status == "VOID"
        assert v.void_reason == ""


# ── B7: editar pagos no dejaba rastro ───────────────────────────────────

@pytest.mark.django_db
class TestB7AuditoriaEdicionPagos:
    def test_queda_registrado_el_antes_y_el_despues(
        self, api_client, tenant, store, warehouse, owner,
    ):
        """Era la única escritura sensible de dinero sin log_audit: cambiar el
        método retroactivamente mueve plata entre efectivo y tarjeta, que es
        justo lo que hay que poder auditar en un cuadre de caja."""
        v = _venta(tenant, store, warehouse, owner, total="10000")
        SalePayment.objects.create(sale=v, tenant=tenant, method="cash", amount=D("10000"))

        r = api_client.patch(
            "/api/sales/sales/%d/payments/" % v.id,
            {"payments": [{"method": "card", "amount": "10000"}]},
            format="json",
        )
        assert r.status_code == 200, r.content

        a = AuditEntry.objects.filter(action="sale_edit_payments", entity_id=v.id).first()
        assert a is not None, "editar pagos debe dejar rastro"
        assert a.detail["before"][0]["method"] == "cash"
        assert a.detail["after"][0]["method"] == "card"


# ── B11: conversión de unidades que fallaba en silencio ─────────────────

@pytest.mark.django_db
class TestB11ConversionSilenciosa:
    def _unit(self, tenant, code, family, factor):
        return Unit.objects.create(
            tenant=tenant, code=code, name=code, family=family,
            conversion_factor=D(str(factor)), is_active=True,
        )

    def test_conversion_normal_funciona(self, tenant):
        kg = self._unit(tenant, "KG", "weight", 1000)
        g = self._unit(tenant, "G", "weight", 1)
        assert convert_qty(D("2"), kg, g) == D("2000")

    def test_factor_cero_ya_no_devuelve_la_cantidad_sin_convertir(self, tenant):
        """ANTES devolvía qty tal cual, en silencio. En un motor que descuenta
        leche en mililitros desde recetas, eso mezcla unidades y corrompe
        consumo, costo y demanda sin que nadie se entere."""
        kg = self._unit(tenant, "KG2", "weight", 1000)
        roto = self._unit(tenant, "ROTO", "weight", 0)
        with pytest.raises(ValueError, match="factor de conversion|factor de conversión"):
            convert_qty(D("2"), kg, roto)

    def test_factor_origen_cero_tambien_falla(self, tenant):
        roto = self._unit(tenant, "ROTO2", "weight", 0)
        g = self._unit(tenant, "G2", "weight", 1)
        with pytest.raises(ValueError, match="factor de conversion|factor de conversión"):
            convert_qty(D("2"), roto, g)

    def test_misma_unidad_no_convierte_ni_falla(self, tenant):
        kg = self._unit(tenant, "KG3", "weight", 1000)
        assert convert_qty(D("5"), kg, kg) == D("5")

    def test_familias_distintas_siguen_fallando(self, tenant):
        kg = self._unit(tenant, "KG4", "weight", 1000)
        lt = self._unit(tenant, "LT4", "volume", 1000)
        with pytest.raises(ValueError):
            convert_qty(D("1"), kg, lt)
