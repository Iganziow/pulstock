"""
tests/test_aislamiento_modulos_nuevos.py — la pasada de aislamiento que faltaba.

El aislamiento entre tenants es MANUAL en cada vista (no hay TenantManager ni
row-level security), así que cada módulo nuevo es una oportunidad de fuga.
El núcleo (catálogo, ventas, stock, bodegas, dashboard) ya tiene pruebas
cross-tenant en test_adversarial.py; los módulos que llegaron después —mesas,
caja, impresión, promociones, forecast— no tenían NINGUNA.

También fija el contrato de store REAL de la app: el store activo es
user.active_store (se cambia desde el Topbar). El header X-Store-Id no se
honra en NINGÚN módulo — stores/middleware.py existe pero nunca se instaló
en MIDDLEWARE. Estos tests impiden que alguien lo "arregle" a medias: o se
instala para toda la app, o para ninguna.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import User, Warehouse
from stores.models import Store

D = Decimal


# ── Tenant B: un competidor con su propio local ─────────────────────────

@pytest.fixture
def tenant_b(db):
    from core.models import Tenant
    t = Tenant(name="Competidor Cafe", slug="competidor-cafe")
    t._skip_subscription = True
    t.save()
    return t


@pytest.fixture
def store_b(db, tenant_b):
    return Store.objects.create(tenant=tenant_b, name="Local Rival")


@pytest.fixture
def warehouse_b(db, tenant_b, store_b):
    return Warehouse.objects.create(tenant=tenant_b, store=store_b, name="Bodega Rival")


@pytest.fixture
def owner_b(db, tenant_b, store_b):
    return User.objects.create(
        username="rival_owner", tenant=tenant_b,
        active_store=store_b, role=User.Role.OWNER,
    )


@pytest.fixture
def client_b(owner_b):
    c = APIClient()
    c.force_authenticate(user=owner_b)
    return c


def _ids(payload):
    filas = payload.get("results", payload) if isinstance(payload, dict) else payload
    return {f["id"] for f in filas}


# ══════════════════════════════════════════════════════════════════════
# MESAS
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def mesa_a(db, tenant, store):
    from tables.models import Table
    return Table.objects.create(tenant=tenant, store=store, name="Mesa VIP", capacity=4)


@pytest.fixture
def orden_a(db, tenant, store, warehouse, mesa_a, owner):
    from tables.models import OpenOrder
    return OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=mesa_a, opened_by=owner, status=OpenOrder.STATUS_OPEN,
    )


@pytest.mark.django_db
class TestMesasAisladas:
    def test_no_ve_las_mesas_del_otro(self, client_b, mesa_a):
        r = client_b.get("/api/tables/tables/")
        assert r.status_code == 200
        assert mesa_a.id not in _ids(r.json())

    def test_no_puede_comandar_en_la_orden_del_otro(self, client_b, orden_a, product):
        r = client_b.post(
            f"/api/tables/orders/{orden_a.id}/add-lines/",
            {"lines": [{"product_id": product.id, "qty": 1}]},
            format="json",
        )
        assert r.status_code == 404, (
            f"comandar en una mesa ajena debe ser 404, fue {r.status_code}"
        )

    def test_no_puede_cobrar_la_mesa_del_otro(self, client_b, orden_a):
        r = client_b.post(
            f"/api/tables/orders/{orden_a.id}/checkout/",
            {"payments": [{"method": "cash", "amount": "0"}]},
            format="json",
        )
        assert r.status_code in (403, 404), (
            f"cobrar una mesa ajena debe fallar, fue {r.status_code}"
        )

    def test_no_puede_ver_la_orden_del_otro(self, client_b, orden_a):
        r = client_b.get(f"/api/tables/orders/{orden_a.id}/")
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# CAJA
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def caja_a(db, tenant, store):
    from caja.models import CashRegister
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja 1")


@pytest.fixture
def sesion_caja_a(db, tenant, caja_a, owner):
    from caja.models import CashSession
    return CashSession.objects.create(
        tenant=tenant, store=caja_a.store, register=caja_a, opened_by=owner,
        initial_amount=D("10000"),
    )


@pytest.mark.django_db
class TestCajaAislada:
    def test_no_ve_las_cajas_del_otro(self, client_b, caja_a):
        r = client_b.get("/api/caja/registers/")
        assert r.status_code == 200
        assert caja_a.id not in _ids(r.json())

    def test_no_puede_ver_la_sesion_del_otro(self, client_b, sesion_caja_a):
        r = client_b.get(f"/api/caja/sessions/{sesion_caja_a.id}/")
        assert r.status_code == 404

    def test_no_puede_meter_movimientos_en_la_caja_del_otro(self, client_b, sesion_caja_a):
        r = client_b.post(
            f"/api/caja/sessions/{sesion_caja_a.id}/movements/",
            {"kind": "OUT", "amount": "5000", "note": "retiro"},
            format="json",
        )
        assert r.status_code in (403, 404), (
            f"mover plata en la caja ajena debe fallar, fue {r.status_code}"
        )

    def test_no_puede_cerrar_la_caja_del_otro(self, client_b, sesion_caja_a):
        r = client_b.post(
            f"/api/caja/sessions/{sesion_caja_a.id}/close/",
            {"counted_amount": "0"}, format="json",
        )
        assert r.status_code in (400, 403, 404)
        sesion_caja_a.refresh_from_db()
        assert sesion_caja_a.status == "OPEN", "la caja ajena no puede quedar cerrada"


# ══════════════════════════════════════════════════════════════════════
# IMPRESIÓN
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def agente_a(db, tenant, store):
    from printing.models import PrintAgent
    return PrintAgent.objects.create(tenant=tenant, store=store, name="PC Caja")


@pytest.mark.django_db
class TestImpresionAislada:
    def test_no_ve_los_agentes_del_otro(self, client_b, agente_a):
        r = client_b.get("/api/printing/agents/")
        assert r.status_code == 200
        assert agente_a.id not in _ids(r.json())

    def test_no_puede_desactivar_el_agente_del_otro(self, client_b, agente_a):
        # El detalle solo expone DELETE (soft-delete): apagarle la impresora
        # al competidor en pleno servicio.
        r = client_b.delete(f"/api/printing/agents/{agente_a.id}/")
        assert r.status_code in (403, 404), f"fue {r.status_code}"
        agente_a.refresh_from_db()
        assert agente_a.is_active, "el agente ajeno no puede quedar desactivado"

    def test_no_puede_regenerar_el_codigo_del_otro(self, client_b, agente_a):
        """Regenerar el código de pareo ajeno = secuestrar su impresora."""
        r = client_b.post(f"/api/printing/agents/{agente_a.id}/regenerate-code/")
        assert r.status_code in (403, 404)


# ══════════════════════════════════════════════════════════════════════
# PROMOCIONES
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def promo_a(db, tenant, store):
    from promotions.models import Promotion
    ahora = timezone.now()
    return Promotion.objects.create(
        tenant=tenant, name="Happy hour",
        discount_type="percent", discount_value=D("20"),
        start_date=ahora, end_date=ahora + datetime.timedelta(days=30),
        is_active=True,
    )


@pytest.mark.django_db
class TestPromocionesAisladas:
    def test_no_ve_las_promos_del_otro(self, client_b, promo_a):
        r = client_b.get("/api/promotions/")
        assert r.status_code == 200
        assert promo_a.id not in _ids(r.json())

    def test_no_puede_editar_la_promo_del_otro(self, client_b, promo_a):
        r = client_b.patch(
            f"/api/promotions/{promo_a.id}/",
            {"discount_value": "90"}, format="json",
        )
        assert r.status_code in (403, 404)
        promo_a.refresh_from_db()
        assert promo_a.discount_value == D("20"), (
            "la promo ajena no puede quedar modificada"
        )


# ══════════════════════════════════════════════════════════════════════
# FORECAST
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def sugerencia_a(db, tenant, warehouse):
    from forecast.models import PurchaseSuggestion
    return PurchaseSuggestion.objects.create(
        tenant=tenant, warehouse=warehouse, status="PENDING",
        total_estimated=D("100000"),
    )


@pytest.fixture
def plan_forecast_b(db, tenant_b):
    """El gating de plan tambien aisla (sin plan: 403 antes de tocar datos),
    pero aca queremos probar el filtro de DATOS: rival CON forecast pago."""
    from billing.models import Plan, Subscription
    plan = Plan.objects.create(name="Pro Rival", price_clp=D("35000"),
                               is_active=True, has_forecast=True)
    ahora = timezone.now()
    return Subscription.objects.create(
        tenant=tenant_b, plan=plan, status=Subscription.Status.ACTIVE,
        current_period_start=ahora,
        current_period_end=ahora + datetime.timedelta(days=30),
    )


@pytest.mark.django_db
class TestForecastAislado:
    def test_sin_plan_forecast_ni_siquiera_entra(self, client_b, sugerencia_a):
        """Primera barrera: el feature-gate del plan responde 403."""
        r = client_b.get("/api/forecast/suggestions/")
        assert r.status_code == 403

    def test_no_ve_las_sugerencias_del_otro(self, client_b, sugerencia_a, plan_forecast_b):
        r = client_b.get("/api/forecast/suggestions/")
        assert r.status_code == 200, r.content
        assert sugerencia_a.id not in _ids(r.json())

    def test_no_puede_aprobar_la_sugerencia_del_otro(self, client_b, sugerencia_a, plan_forecast_b):
        """Aprobar una sugerencia ajena crearía una compra en el negocio ajeno."""
        r = client_b.post(f"/api/forecast/suggestions/{sugerencia_a.id}/approve/")
        assert r.status_code in (400, 403, 404)
        sugerencia_a.refresh_from_db()
        assert sugerencia_a.status == "PENDING"


# ══════════════════════════════════════════════════════════════════════
# REPORTES: aislamiento entre tenants Y contrato de store
# ══════════════════════════════════════════════════════════════════════

def _venta(tenant, store, warehouse, user, total):
    from sales.models import Sale
    return Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=user,
        subtotal=D(total), total=D(total), status="COMPLETED", sale_type="VENTA",
    )


@pytest.mark.django_db
class TestReportesAislados:
    def test_el_resumen_no_mezcla_tenants(
        self, api_client, client_b, tenant, store, warehouse, owner,
        tenant_b, store_b, warehouse_b, owner_b,
    ):
        _venta(tenant, store, warehouse, owner, "111111")
        _venta(tenant_b, store_b, warehouse_b, owner_b, "77777")

        r = client_b.get("/api/reports/sales-summary/")
        assert r.status_code == 200, r.content
        cuerpo = r.content.decode()
        assert "111111" not in cuerpo, "el resumen del rival muestra ventas ajenas"

    def test_cambiar_de_local_cambia_el_reporte(
        self, tenant, store, warehouse, owner,
    ):
        """El contrato real: el scope de reportes es user.active_store."""
        local2 = Store.objects.create(tenant=tenant, name="Local Dos")
        bodega2 = Warehouse.objects.create(tenant=tenant, store=local2, name="Bodega Dos")
        _venta(tenant, store, warehouse, owner, "111111")
        _venta(tenant, local2, bodega2, owner, "222222")

        cliente = APIClient()
        cliente.force_authenticate(user=owner)

        r = cliente.get("/api/reports/sales-summary/")
        cuerpo = r.content.decode()
        assert "111111" in cuerpo and "222222" not in cuerpo

        owner.active_store = local2
        owner.save(update_fields=["active_store"])
        r = cliente.get("/api/reports/sales-summary/")
        cuerpo = r.content.decode()
        assert "222222" in cuerpo, "cambié de local: deben aparecer sus ventas"
        assert "111111" not in cuerpo, "el local anterior no puede seguir apareciendo"

    def test_x_store_id_se_ignora_de_forma_consistente(
        self, api_client, tenant, store, warehouse, owner,
    ):
        """X-Store-Id es código muerto en TODA la app (el middleware que lo
        leería no está instalado). Este test fija esa uniformidad: si alguien
        instala el middleware o hace que UN módulo lo lea, esto se cae y
        obliga a decidirlo para la app completa — scopear reportes distinto
        que ventas/caja/mesas sería peor que cualquiera de los dos mundos."""
        local2 = Store.objects.create(tenant=tenant, name="Local Dos")
        bodega2 = Warehouse.objects.create(tenant=tenant, store=local2, name="Bodega Dos")
        _venta(tenant, store, warehouse, owner, "111111")
        _venta(tenant, local2, bodega2, owner, "222222")

        r = api_client.get("/api/reports/sales-summary/", HTTP_X_STORE_ID=str(local2.id))
        cuerpo = r.content.decode()
        assert "111111" in cuerpo and "222222" not in cuerpo, (
            "el header cambió el scope de reportes: alguien lo cableó a medias"
        )

    def test_un_store_ajeno_en_el_header_no_da_datos_ajenos(
        self, client_b, tenant, store, warehouse, owner,
        tenant_b, store_b, warehouse_b, owner_b,
    ):
        """Y aunque el header se ignore, que quede fijado: el store de OTRO
        tenant en el header jamás produce datos ajenos."""
        _venta(tenant, store, warehouse, owner, "111111")
        _venta(tenant_b, store_b, warehouse_b, owner_b, "77777")

        r = client_b.get("/api/reports/sales-summary/", HTTP_X_STORE_ID=str(store.id))
        assert r.status_code == 200, r.content
        cuerpo = r.content.decode()
        assert "111111" not in cuerpo, (
            "con el store de otro tenant en el header se filtraron sus ventas"
        )
        assert "77777" in cuerpo, "debe seguir viendo lo propio"
