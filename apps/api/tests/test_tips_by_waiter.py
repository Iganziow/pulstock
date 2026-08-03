"""
tests/test_tips_by_waiter.py — Total de propinas POR GARZÓN en el resumen.

Mario (03/08/26): "Se puede cambiar el garzón por venta, pero no cambia el
monto de propinas según garzón corregido al final del periodo seleccionado."
Causa: el resumen solo tenía `by_cashier` (quien COBRÓ). El reparto de propinas
se hace por quien ATENDIÓ → faltaba `by_waiter`.

Batería pedida: cambiar el garzón, ver que se recargue, que NO falte plata,
y volver a cambiarlo a otro (ida y vuelta) sin perder montos.
"""
import pytest
from decimal import Decimal

from rest_framework.test import APIClient

from core.models import User
from tables.models import Table, OpenOrder
from sales.models import Sale, SaleTip

URL_SUMMARY = "/api/sales/tips-summary/"


def _waiter_url(pk):
    return f"/api/sales/sales/{pk}/waiter/"


def _mk_user(tenant, store, username, role=User.Role.CASHIER, first="", last=""):
    u = User.objects.create_user(username=username, password="x", first_name=first, last_name=last)
    u.tenant = tenant
    u.active_store = store
    u.role = role
    u.save(update_fields=["tenant", "active_store", "role"])
    return u


def _sale_con_propina(tenant, store, warehouse, owner, waiter, tip, total="10000", open_order=None):
    s = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        subtotal=Decimal(total), total=Decimal(total), tip=Decimal(str(tip)),
        status="COMPLETED", sale_type="VENTA", waiter=waiter, open_order=open_order,
    )
    SaleTip.objects.create(sale=s, tenant=tenant, method="cash", amount=Decimal(str(tip)))
    return s


def _by_waiter(api_client):
    r = api_client.get(URL_SUMMARY)
    assert r.status_code == 200, r.content
    data = r.json()
    return {row["name"]: Decimal(row["total"]) for row in data["by_waiter"]}, data


# ── El resumen expone by_waiter ────────────────────────────────────────────

@pytest.mark.django_db
def test_summary_incluye_by_waiter(api_client, tenant, store, warehouse, owner):
    gar_a = _mk_user(tenant, store, "gar_a", first="Ana", last="Alfa")
    gar_b = _mk_user(tenant, store, "gar_b", first="Beto", last="Beta")
    _sale_con_propina(tenant, store, warehouse, owner, gar_a, 1000)
    _sale_con_propina(tenant, store, warehouse, owner, gar_a, 500)
    _sale_con_propina(tenant, store, warehouse, owner, gar_b, 800)

    tot, data = _by_waiter(api_client)
    assert tot["Ana Alfa"] == Decimal("1500")
    assert tot["Beto Beta"] == Decimal("800")
    # La plata total cuadra con la suma por garzón
    assert sum(tot.values()) == Decimal(data["total_tips"]) == Decimal("2300")


@pytest.mark.django_db
def test_ventas_sin_garzon_agrupan_aparte(api_client, tenant, store, warehouse, owner):
    """Mostrador sin garzón: la plata NO se pierde, va a 'Sin garzón'."""
    gar = _mk_user(tenant, store, "gar_solo", first="Ana", last="Alfa")
    _sale_con_propina(tenant, store, warehouse, owner, gar, 1000)
    _sale_con_propina(tenant, store, warehouse, owner, None, 700)  # mostrador

    tot, data = _by_waiter(api_client)
    assert tot["Ana Alfa"] == Decimal("1000")
    assert tot["Sin garzón"] == Decimal("700")
    assert sum(tot.values()) == Decimal(data["total_tips"]) == Decimal("1700")


# ── LO QUE PIDIÓ MARIO: cambiar garzón y ver que el total se mueva ─────────

@pytest.mark.django_db
def test_al_corregir_garzon_la_propina_se_mueve(api_client, tenant, store, warehouse, owner):
    gar_a = _mk_user(tenant, store, "gar_mov_a", first="Ana", last="Alfa")
    gar_b = _mk_user(tenant, store, "gar_mov_b", first="Beto", last="Beta")
    venta = _sale_con_propina(tenant, store, warehouse, owner, gar_a, 1200)

    antes, d1 = _by_waiter(api_client)
    assert antes["Ana Alfa"] == Decimal("1200")
    assert "Beto Beta" not in antes

    # Corregir: era Beto quien atendió
    r = api_client.patch(_waiter_url(venta.id), {"waiter_id": gar_b.id}, format="json")
    assert r.status_code == 200, r.content

    despues, d2 = _by_waiter(api_client)
    assert despues["Beto Beta"] == Decimal("1200")   # se movió
    assert "Ana Alfa" not in despues                  # ya no figura
    # NO FALTA PLATA: el total del período no cambió
    assert Decimal(d2["total_tips"]) == Decimal(d1["total_tips"]) == Decimal("1200")


@pytest.mark.django_db
def test_ida_y_vuelta_entre_garzones_sin_perder_plata(api_client, tenant, store, warehouse, owner):
    """Cambiar A→B→C→A: en cada paso el total del período se mantiene."""
    a = _mk_user(tenant, store, "gv_a", first="Ana", last="A")
    b = _mk_user(tenant, store, "gv_b", first="Beto", last="B")
    c = _mk_user(tenant, store, "gv_c", first="Caro", last="C")
    venta = _sale_con_propina(tenant, store, warehouse, owner, a, 900)
    # Otra venta de control que NO se toca
    _sale_con_propina(tenant, store, warehouse, owner, c, 300)

    esperado_total = Decimal("1200")
    for destino, nombre in [(b, "Beto B"), (c, "Caro C"), (a, "Ana A")]:
        r = api_client.patch(_waiter_url(venta.id), {"waiter_id": destino.id}, format="json")
        assert r.status_code == 200, r.content
        tot, data = _by_waiter(api_client)
        # La plata total NUNCA cambia
        assert Decimal(data["total_tips"]) == esperado_total
        assert sum(tot.values()) == esperado_total
        # El garzón destino tiene al menos los 900 movidos
        assert tot[nombre] >= Decimal("900")

    # Estado final: volvió a Ana (900) y Caro conserva su venta de control (300)
    tot, _ = _by_waiter(api_client)
    assert tot["Ana A"] == Decimal("900")
    assert tot["Caro C"] == Decimal("300")


@pytest.mark.django_db
def test_quitar_garzon_manda_la_plata_a_sin_garzon(api_client, tenant, store, warehouse, owner):
    gar = _mk_user(tenant, store, "gar_quitar", first="Ana", last="Alfa")
    venta = _sale_con_propina(tenant, store, warehouse, owner, gar, 500)

    r = api_client.patch(_waiter_url(venta.id), {"waiter_id": None}, format="json")
    assert r.status_code == 200, r.content
    tot, data = _by_waiter(api_client)
    assert tot["Sin garzón"] == Decimal("500")
    assert Decimal(data["total_tips"]) == Decimal("500")  # no se perdió


@pytest.mark.django_db
def test_mesa_con_varias_ventas_mueve_todas(api_client, tenant, store, warehouse, owner):
    """Cobro parcial: al corregir el garzón, TODAS las propinas de esa mesa se mueven."""
    a = _mk_user(tenant, store, "gm_a", first="Ana", last="A")
    b = _mk_user(tenant, store, "gm_b", first="Beto", last="B")
    table = Table.objects.create(tenant=tenant, store=store, name="M-tips")
    order = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table, opened_by=owner, waiter=a, status="CLOSED",
    )
    v1 = _sale_con_propina(tenant, store, warehouse, owner, a, 400, open_order=order)
    _sale_con_propina(tenant, store, warehouse, owner, a, 600, open_order=order)

    tot, _ = _by_waiter(api_client)
    assert tot["Ana A"] == Decimal("1000")

    api_client.patch(_waiter_url(v1.id), {"waiter_id": b.id}, format="json")

    tot, data = _by_waiter(api_client)
    assert tot["Beto B"] == Decimal("1000")  # las DOS ventas de la mesa
    assert "Ana A" not in tot
    assert Decimal(data["total_tips"]) == Decimal("1000")


@pytest.mark.django_db
def test_venta_anulada_no_suma_a_ningun_garzon(api_client, tenant, store, warehouse, owner):
    """Al anular, la propina sale del total y del garzón (sin dejar fantasma)."""
    gar = _mk_user(tenant, store, "gar_void", first="Ana", last="Alfa")
    venta = _sale_con_propina(tenant, store, warehouse, owner, gar, 800)
    _sale_con_propina(tenant, store, warehouse, owner, gar, 200)

    tot, _ = _by_waiter(api_client)
    assert tot["Ana Alfa"] == Decimal("1000")

    r = api_client.post(f"/api/sales/sales/{venta.id}/void/", {"reason": "test"}, format="json")
    assert r.status_code == 200, r.content

    tot, data = _by_waiter(api_client)
    assert tot["Ana Alfa"] == Decimal("200")
    assert Decimal(data["total_tips"]) == Decimal("200")


@pytest.mark.django_db
def test_filtro_por_garzon_coincide_con_su_total(api_client, tenant, store, warehouse, owner):
    """Filtrar por un garzón debe dar exactamente lo que muestra su fila."""
    a = _mk_user(tenant, store, "gf_a", first="Ana", last="A")
    b = _mk_user(tenant, store, "gf_b", first="Beto", last="B")
    _sale_con_propina(tenant, store, warehouse, owner, a, 700)
    _sale_con_propina(tenant, store, warehouse, owner, b, 300)

    tot, _ = _by_waiter(api_client)
    r = api_client.get(f"{URL_SUMMARY}?waiter={a.id}")
    assert Decimal(r.json()["total_tips"]) == tot["Ana A"] == Decimal("700")


@pytest.mark.django_db
def test_resumen_y_tabla_cuadran_con_los_mismos_filtros(api_client, tenant, store, warehouse, owner):
    """El resumen acepta cashier_id (alias) igual que la tabla → misma plata.

    Si no, el 'total por garzón' mostraría más que la tabla filtrada.
    """
    otro_cajero = _mk_user(tenant, store, "cajero2", role=User.Role.CASHIER)
    gar = _mk_user(tenant, store, "gar_cuadre", first="Ana", last="A")
    _sale_con_propina(tenant, store, warehouse, owner, gar, 500)
    s2 = _sale_con_propina(tenant, store, warehouse, owner, gar, 300)
    Sale.objects.filter(id=s2.id).update(created_by=otro_cajero)

    resumen = api_client.get(f"{URL_SUMMARY}?cashier_id={owner.id}").json()
    tabla = api_client.get(f"/api/sales/tips-list/?cashier_id={owner.id}").json()
    assert Decimal(resumen["total_tips"]) == Decimal(tabla["totals"]["total_tips"]) == Decimal("500")
    por_garzon = {r["name"]: Decimal(r["total"]) for r in resumen["by_waiter"]}
    assert por_garzon["Ana A"] == Decimal("500")  # solo la venta del cajero filtrado
