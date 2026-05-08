"""
Tests del fix de promo en mesas (08/05/26).

Bug reportado por Mario: agregaba un Chocman 33gr a una mesa "Para llevar"
con una promo activa de 30%. El item aparecía en la mesa por $500 (precio
del catálogo) en vez de $350 (con promo). El cobro final SÍ aplicaba la
promo, pero la mesa mostraba el precio "incorrecto" durante todo el flujo.

Fix: el endpoint POST /tables/orders/{id}/add-lines/ ahora resuelve las
promos activas y fuerza el promo_price si el frontend envió un precio
mayor (mismo criterio que sales/pricing.py en el POS de barra).
"""
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from core.models import Warehouse
from promotions.models import Promotion, PromotionProduct
from tables.models import Table, OpenOrder, OpenOrderLine


@pytest.fixture
def warehouse_t(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="W-Tables")


@pytest.fixture
def chocman(db, tenant):
    return Product.objects.create(
        tenant=tenant, name="Chocman 33gr", price=Decimal("500"),
        is_active=True, sku="CHOC-33",
    )


@pytest.fixture
def open_table_order(db, tenant, store, warehouse_t, owner):
    table = Table.objects.create(
        tenant=tenant, store=store, name="Mesa 3",
        status=Table.STATUS_OPEN,
    )
    return OpenOrder.objects.create(
        tenant=tenant, store=store, table=table,
        warehouse=warehouse_t, status=OpenOrder.STATUS_OPEN,
        opened_by=owner,
    )


@pytest.fixture
def active_30pct_promo(db, tenant, chocman):
    promo = Promotion.objects.create(
        tenant=tenant, name="30% off Chocman",
        discount_type="pct", discount_value=Decimal("30"),
        start_date=timezone.now() - timedelta(hours=1),
        end_date=timezone.now() + timedelta(days=7),
        is_active=True,
    )
    PromotionProduct.objects.create(promotion=promo, product=chocman)
    return promo


@pytest.mark.django_db
class TestAddLinesAppliesPromo:
    """El endpoint que usa la mesa al agregar items debe forzar el
    promo_price cuando hay promo activa."""

    def test_chocman_with_active_30pct_saves_at_350_not_500(
        self, api_client, open_table_order, chocman, active_30pct_promo,
    ):
        """Mario manda unit_price=500 (precio normal). Backend debe
        guardar 350 (con 30% off aplicado)."""
        url = f"/api/tables/orders/{open_table_order.id}/add-lines/"
        resp = api_client.post(url, {
            "lines": [
                {"product_id": chocman.id, "qty": "1", "unit_price": "500", "note": ""},
            ],
        }, format="json")
        assert resp.status_code == 201, resp.content

        line = OpenOrderLine.objects.get(order=open_table_order, product=chocman)
        assert line.unit_price == Decimal("350"), (
            f"Esperaba $350 (500 con 30% off). Obtuve {line.unit_price}. "
            f"El fix de promo en /add-lines/ no se aplicó."
        )

    def test_no_promo_keeps_original_price(
        self, api_client, open_table_order, chocman,
    ):
        """Si NO hay promo activa, el precio enviado se respeta."""
        url = f"/api/tables/orders/{open_table_order.id}/add-lines/"
        resp = api_client.post(url, {
            "lines": [
                {"product_id": chocman.id, "qty": "1", "unit_price": "500", "note": ""},
            ],
        }, format="json")
        assert resp.status_code == 201
        line = OpenOrderLine.objects.get(order=open_table_order, product=chocman)
        assert line.unit_price == Decimal("500")

    def test_manual_lower_price_respected(
        self, api_client, open_table_order, chocman, active_30pct_promo,
    ):
        """Si el cajero baja MANUALMENTE el precio por debajo del promo
        (ej: cortesía), se respeta. Solo bajamos automáticamente,
        nunca subimos al cobro manual."""
        url = f"/api/tables/orders/{open_table_order.id}/add-lines/"
        resp = api_client.post(url, {
            "lines": [
                {"product_id": chocman.id, "qty": "1", "unit_price": "200", "note": "cortesía"},
            ],
        }, format="json")
        assert resp.status_code == 201
        line = OpenOrderLine.objects.get(order=open_table_order, product=chocman)
        assert line.unit_price == Decimal("200"), (
            "Si el cajero pone 200 manual, NO subimos a 350 promo."
        )

    def test_inactive_promo_not_applied(
        self, api_client, open_table_order, chocman, tenant,
    ):
        """Una promo desactivada (is_active=False) no se aplica."""
        promo = Promotion.objects.create(
            tenant=tenant, name="Desactivada",
            discount_type="pct", discount_value=Decimal("50"),
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(days=7),
            is_active=False,  # ← desactivada
        )
        PromotionProduct.objects.create(promotion=promo, product=chocman)

        url = f"/api/tables/orders/{open_table_order.id}/add-lines/"
        resp = api_client.post(url, {
            "lines": [
                {"product_id": chocman.id, "qty": "1", "unit_price": "500", "note": ""},
            ],
        }, format="json")
        assert resp.status_code == 201
        line = OpenOrderLine.objects.get(order=open_table_order, product=chocman)
        assert line.unit_price == Decimal("500"), "Promo desactivada NO debe aplicarse"

    def test_future_promo_not_applied(
        self, api_client, open_table_order, chocman, tenant,
    ):
        """Una promo programada para mañana no se aplica hoy."""
        promo = Promotion.objects.create(
            tenant=tenant, name="Mañana",
            discount_type="pct", discount_value=Decimal("50"),
            start_date=timezone.now() + timedelta(days=1),  # ← futuro
            end_date=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        PromotionProduct.objects.create(promotion=promo, product=chocman)

        url = f"/api/tables/orders/{open_table_order.id}/add-lines/"
        resp = api_client.post(url, {
            "lines": [
                {"product_id": chocman.id, "qty": "1", "unit_price": "500", "note": ""},
            ],
        }, format="json")
        line = OpenOrderLine.objects.get(order=open_table_order, product=chocman)
        assert line.unit_price == Decimal("500")
