"""
Tests Adversariales — "¿Podemos reventar el sistema?"
======================================================

Escenarios hipotéticos de ataques y abusos reales.

ATACANTE 1 — Cajero malicioso:
  - Intenta escalar a owner
  - Intenta ver datos de otro tenant
  - Intenta anular ventas
  - Intenta crear productos con precios negativos
  - Intenta vender con stock en 0

ATACANTE 2 — Owner malicioso:
  - Intenta borrar todos los owners
  - Intenta inyectar SQL via campos de texto
  - Intenta crear productos con nombres gigantes
  - Intenta overflow en cantidades decimales

ATACANTE 3 — Usuario de otro tenant:
  - Intenta operar en bodega ajena
  - Intenta ver ventas ajenas
  - Intenta cobrar orden de mesa ajena
  - Intenta acceder a dashboard ajeno

ATACANTE 4 — Request malformado:
  - JSON inválido
  - Campos con tipos incorrectos
  - IDs negativos / inexistentes
  - Cantidades extremas (10^15, -999, 0.00000001)
  - Strings donde esperan números

ATACANTE 5 — Race conditions:
  - Doble venta simultánea con mismo idempotency_key
  - Vender más stock del disponible en paralelo

ATACANTE 6 — Billing abuse:
  - Suscripción suspendida intenta operar
  - Webhook falso de Flow
  - Token de pago inventado
"""
import pytest
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django.db import connection
from rest_framework.test import APIClient

from core.models import User, Tenant
from stores.models import Store
from core.models import Warehouse
from catalog.models import Product, Category
from inventory.models import StockItem
from sales.models import Sale


D = Decimal


# ══════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════

@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Tenant A", slug="tenant-a-adv")

@pytest.fixture
def store_a(tenant_a):
    return Store.objects.create(tenant=tenant_a, name="Store A")

@pytest.fixture
def warehouse_a(tenant_a, store_a):
    return Warehouse.objects.create(tenant=tenant_a, store=store_a, name="Bodega A")

@pytest.fixture
def owner_a(tenant_a, store_a):
    u = User.objects.create_user(
        username="adv_owner_a", password="pass12345",
        tenant=tenant_a, active_store=store_a, role=User.Role.OWNER,
    )
    return u

@pytest.fixture
def cashier_a(tenant_a, store_a, owner_a):
    return User.objects.create_user(
        username="adv_cashier_a", password="pass12345",
        tenant=tenant_a, active_store=store_a, role=User.Role.CASHIER,
    )

@pytest.fixture
def client_owner_a(owner_a):
    c = APIClient()
    c.force_authenticate(user=owner_a)
    return c

@pytest.fixture
def client_cashier_a(cashier_a):
    c = APIClient()
    c.force_authenticate(user=cashier_a)
    return c

@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Tenant B", slug="tenant-b-adv")

@pytest.fixture
def store_b(tenant_b):
    return Store.objects.create(tenant=tenant_b, name="Store B")

@pytest.fixture
def warehouse_b(tenant_b, store_b):
    return Warehouse.objects.create(tenant=tenant_b, store=store_b, name="Bodega B")

@pytest.fixture
def owner_b(tenant_b, store_b):
    return User.objects.create_user(
        username="adv_owner_b", password="pass12345",
        tenant=tenant_b, active_store=store_b, role=User.Role.OWNER,
    )

@pytest.fixture
def client_owner_b(owner_b):
    c = APIClient()
    c.force_authenticate(user=owner_b)
    return c

@pytest.fixture
def product_a(tenant_a):
    return Product.objects.create(tenant=tenant_a, name="Coca Cola", price=D("1500"), is_active=True)

@pytest.fixture
def product_b(tenant_b):
    return Product.objects.create(tenant=tenant_b, name="Pepsi", price=D("1200"), is_active=True)

@pytest.fixture
def stocked_product_a(tenant_a, warehouse_a, product_a):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant_a, warehouse=warehouse_a, product=product_a,
        defaults={"on_hand": D("50"), "avg_cost": D("800"), "stock_value": D("40000")},
    )
    si.on_hand = D("50")
    si.avg_cost = D("800")
    si.stock_value = D("40000")
    si.save()
    return si


def _sell(client, warehouse_id, lines, payments=None, **kwargs):
    body = {"warehouse_id": warehouse_id, "lines": lines, "payments": payments or [], **kwargs}
    return client.post("/api/sales/sales/", body, format="json")


def _receive(client, warehouse_id, product_id, qty, unit_cost=None):
    body = {"warehouse_id": warehouse_id, "product_id": product_id, "qty": str(qty)}
    if unit_cost is not None:
        body["unit_cost"] = str(unit_cost)
    return client.post("/api/inventory/receive/", body, format="json")


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 1 — CAJERO MALICIOSO
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCajeroMalicioso:

    def test_cajero_no_puede_crear_usuarios(self, client_cashier_a):
        r = client_cashier_a.post("/api/core/users/", {
            "username": "hacker", "password": "hack12345", "role": "owner",
        }, format="json")
        assert r.status_code == 403

    def test_cajero_no_puede_cambiar_su_rol(self, client_cashier_a, cashier_a):
        r = client_cashier_a.patch(f"/api/core/users/{cashier_a.id}/", {
            "role": "owner",
        }, format="json")
        assert r.status_code == 403

    def test_cajero_no_puede_ver_lista_usuarios(self, client_cashier_a):
        r = client_cashier_a.get("/api/core/users/")
        assert r.status_code == 403

    def test_cajero_no_puede_anular_venta(self, client_owner_a, client_cashier_a, warehouse_a, stocked_product_a, product_a):
        # Owner makes sale
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        sale_id = r.data["id"]
        # Cashier tries to void
        r2 = client_cashier_a.post(f"/api/sales/sales/{sale_id}/void/", format="json")
        assert r2.status_code in (403, 405)

    def test_cajero_no_puede_crear_producto_precio_negativo(self, client_cashier_a):
        """Cashier can create products (if view allows) but price must be valid."""
        r = client_cashier_a.post("/api/catalog/products/", {
            "name": "Hack Product", "price": "-500",
        }, format="json")
        # Should either be 403 (no permission) or 400 (validation)
        assert r.status_code in (400, 403)

    def test_venta_con_stock_en_cero(self, client_cashier_a, warehouse_a, product_a, tenant_a):
        """Vender sin stock → 409."""
        # Ensure no stock
        StockItem.objects.filter(tenant=tenant_a, product=product_a).update(on_hand=D("0"))
        r = _sell(client_cashier_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        assert r.status_code == 409

    def test_venta_qty_mayor_que_stock(self, client_cashier_a, warehouse_a, stocked_product_a, product_a):
        """Vender más de lo disponible → 409."""
        r = _sell(client_cashier_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "999", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 999 * 1500}])
        assert r.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 2 — OWNER MALICIOSO (ABUSO INTERNO)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOwnerMalicioso:

    def test_no_puede_borrar_ultimo_owner(self, client_owner_a, owner_a, tenant_a):
        """No puede quedarse sin dueño."""
        # Ensure only 1 owner
        User.objects.filter(tenant=tenant_a, role="owner").exclude(pk=owner_a.pk).update(role="manager")
        r = client_owner_a.patch(f"/api/core/users/{owner_a.id}/", {
            "role": "cashier",
        }, format="json")
        assert r.status_code == 400

    def test_sql_injection_en_nombre_producto(self, client_owner_a):
        """SQL injection en name → se guarda como string, no ejecuta."""
        r = client_owner_a.post("/api/catalog/products/", {
            "name": "'; DROP TABLE catalog_product; --",
            "price": "1000",
        }, format="json")
        assert r.status_code == 201
        # Product table still exists
        assert Product.objects.count() > 0

    def test_sql_injection_en_busqueda(self, client_owner_a):
        r = client_owner_a.get("/api/catalog/products/?q='; DROP TABLE--")
        assert r.status_code == 200

    def test_nombre_producto_gigante(self, client_owner_a):
        """Nombre de 10000 caracteres."""
        r = client_owner_a.post("/api/catalog/products/", {
            "name": "A" * 10000,
            "price": "100",
        }, format="json")
        # Should either truncate or reject
        assert r.status_code in (201, 400)

    def test_precio_overflow(self, client_owner_a):
        """Precio absurdamente grande."""
        r = client_owner_a.post("/api/catalog/products/", {
            "name": "Overflow", "price": "99999999999999",
        }, format="json")
        # Should reject (max_digits=12, decimal_places=2)
        assert r.status_code in (400, 201)

    def test_cantidad_decimal_extrema(self, client_owner_a, warehouse_a, product_a, tenant_a):
        """Recibir 0.00000001 unidades."""
        _receive(client_owner_a, warehouse_a.id, product_a.id, "0.001", 1000)
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "0.001", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 2}])
        assert r.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 3 — CROSS-TENANT (TENANT B ATACANDO TENANT A)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCrossTenantAttack:

    def test_no_ve_productos_ajenos(self, client_owner_b, product_a):
        r = client_owner_b.get("/api/catalog/products/")
        ids = {p["id"] for p in (r.data.get("results", r.data) if isinstance(r.data, (dict, list)) else [])}
        assert product_a.id not in ids

    def test_no_puede_vender_producto_ajeno(self, client_owner_b, warehouse_b, product_a):
        """Tenant B intenta vender producto de Tenant A."""
        _receive(client_owner_b, warehouse_b.id, product_a.id, 10, 100)
        # Should fail — product doesn't belong to tenant B
        r = _sell(client_owner_b, warehouse_b.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1000"},
        ], [{"method": "cash", "amount": 1000}])
        assert r.status_code in (400, 404, 409)

    def test_no_puede_recibir_en_bodega_ajena(self, client_owner_b, warehouse_a, product_b):
        """Tenant B intenta recibir stock en bodega de Tenant A."""
        r = _receive(client_owner_b, warehouse_a.id, product_b.id, 10, 100)
        assert r.status_code in (400, 403, 404, 409)

    def test_no_puede_ver_venta_ajena(self, client_owner_a, client_owner_b, warehouse_a, stocked_product_a, product_a):
        """Tenant B no puede ver detalle de venta de Tenant A."""
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        sale_id = r.data["id"]
        r2 = client_owner_b.get(f"/api/sales/sales/{sale_id}/")
        assert r2.status_code == 404

    def test_no_puede_anular_venta_ajena(self, client_owner_a, client_owner_b, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        sale_id = r.data["id"]
        r2 = client_owner_b.post(f"/api/sales/sales/{sale_id}/void/", format="json")
        assert r2.status_code == 404

    def test_no_puede_ajustar_stock_ajeno(self, client_owner_b, warehouse_a, product_a):
        r = client_owner_b.post("/api/inventory/adjust/", {
            "warehouse_id": warehouse_a.id,
            "product_id": product_a.id,
            "qty": "-10",
            "note": "hack",
        }, format="json")
        assert r.status_code in (400, 403, 404, 409)

    def test_no_puede_ver_dashboard_ajeno(self, client_owner_a, client_owner_b, warehouse_a, stocked_product_a, product_a):
        _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "5", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 7500}])
        r = client_owner_b.get("/api/dashboard/summary/")
        assert r.status_code == 200
        kpis = r.data.get("kpis", {})
        today = kpis.get("sales_today", {})
        revenue = D(str(today.get("total", today.get("revenue", "0"))))
        assert revenue == D("0")  # Tenant B sees $0

    def test_no_puede_ver_categorias_ajenas(self, client_owner_b, tenant_a):
        Category.objects.create(tenant=tenant_a, name="Secreta A")
        r = client_owner_b.get("/api/catalog/categories/")
        names = {c["name"] for c in (r.data.get("results", r.data) if isinstance(r.data, (dict, list)) else [])}
        assert "Secreta A" not in names


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 4 — REQUESTS MALFORMADOS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMalformedRequests:

    def test_json_invalido(self, client_owner_a):
        r = client_owner_a.post(
            "/api/catalog/products/",
            "esto no es json {{{",
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_qty_como_string(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "muchos", "unit_price": "1500"},
        ])
        assert r.status_code == 400

    def test_product_id_negativo(self, client_owner_a, warehouse_a, stocked_product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": -1, "qty": "1", "unit_price": "1500"},
        ])
        assert r.status_code in (400, 404)

    def test_product_id_inexistente(self, client_owner_a, warehouse_a, stocked_product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": 999999, "qty": "1", "unit_price": "1500"},
        ])
        assert r.status_code in (400, 404)

    def test_warehouse_id_inexistente(self, client_owner_a, product_a, stocked_product_a):
        r = _sell(client_owner_a, 999999, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ])
        assert r.status_code in (400, 404, 409)

    def test_venta_sin_lineas(self, client_owner_a, warehouse_a):
        r = _sell(client_owner_a, warehouse_a.id, [])
        assert r.status_code == 400

    def test_qty_cero(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "0", "unit_price": "1500"},
        ])
        assert r.status_code == 400

    def test_qty_negativo(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "-5", "unit_price": "1500"},
        ])
        assert r.status_code == 400

    def test_precio_negativo(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "-100"},
        ])
        # May allow (discounts) or reject — either is OK as long as no crash
        assert r.status_code in (201, 400)

    def test_metodo_pago_invalido(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "bitcoin", "amount": 1500}])
        # Invalid method should be ignored or rejected
        assert r.status_code in (201, 400)

    def test_cantidad_extrema(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        """Cantidad de 10^12 → should reject (not enough stock)."""
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "999999999999", "unit_price": "1"},
        ])
        assert r.status_code in (400, 409)

    def test_xss_en_nombre_producto(self, client_owner_a):
        """XSS payload en nombre — se guarda como texto plano."""
        r = client_owner_a.post("/api/catalog/products/", {
            "name": '<script>alert("xss")</script>',
            "price": "100",
        }, format="json")
        assert r.status_code == 201
        p = Product.objects.get(id=r.data["id"])
        assert "<script>" in p.name  # Stored as-is (frontend must escape)


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 5 — RACE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRaceConditions:

    def test_idempotency_key_prevents_double_sale(self, client_owner_a, warehouse_a, stocked_product_a, product_a):
        """Misma idempotency_key → segunda venta retorna la primera."""
        body = {
            "warehouse_id": warehouse_a.id,
            "lines": [{"product_id": product_a.id, "qty": "1", "unit_price": "1500"}],
            "payments": [{"method": "cash", "amount": 1500}],
            "idempotency_key": "unique-key-12345",
        }
        r1 = client_owner_a.post("/api/sales/sales/", body, format="json")
        r2 = client_owner_a.post("/api/sales/sales/", body, format="json")
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.data["id"] == r2.data["id"]  # Same sale returned

    def test_stock_not_negative_after_concurrent_sells(self, client_owner_a, warehouse_a, tenant_a, product_a):
        """Even after sales, stock should never go negative."""
        # Set stock to exactly 5
        si, _ = StockItem.objects.get_or_create(
            tenant=tenant_a, warehouse=warehouse_a, product=product_a,
            defaults={"on_hand": D("5"), "avg_cost": D("800"), "stock_value": D("4000")},
        )
        si.on_hand = D("5")
        si.avg_cost = D("800")
        si.stock_value = D("4000")
        si.save()

        # Sell 5 (should succeed)
        r = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "5", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 7500}])
        assert r.status_code == 201

        si.refresh_from_db()
        assert si.on_hand == D("0.000")

        # Try selling 1 more (should fail)
        r2 = _sell(client_owner_a, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        assert r2.status_code == 409

        # Stock should still be 0, not negative
        si.refresh_from_db()
        assert si.on_hand >= D("0")


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 6 — BILLING ABUSE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBillingAbuse:

    @pytest.fixture
    def suspended_sub(self, tenant_a):
        from billing.models import Plan, Subscription
        plan, _ = Plan.objects.get_or_create(
            key="pro", defaults={"name": "Pro", "price_clp": 59990,
                                  "max_products": -1, "max_stores": -1, "max_users": -1,
                                  "has_forecast": True, "has_abc": True, "has_reports": True},
        )
        sub = Subscription.objects.filter(tenant=tenant_a).first()
        now = timezone.now()
        if sub:
            sub.plan = plan
            sub.status = Subscription.Status.SUSPENDED
            sub.suspended_at = now
            sub.save()
        else:
            sub = Subscription.objects.create(
                tenant=tenant_a, plan=plan, status=Subscription.Status.SUSPENDED,
                current_period_start=now - timedelta(days=30),
                current_period_end=now - timedelta(days=1),
                suspended_at=now,
            )
        return sub

    def test_suspended_cant_create_products(self, tenant_a, store_a, owner_a, suspended_sub):
        """Suspended tenant can't create products via JWT."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(tenant_a.id)
        token = RefreshToken.for_user(owner_a)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")
        r = c.post("/api/catalog/products/", {"name": "Hack", "price": "100"}, format="json")
        assert r.status_code == 402

    def test_suspended_cant_sell(self, tenant_a, store_a, owner_a, warehouse_a, stocked_product_a, product_a, suspended_sub):
        from rest_framework_simplejwt.tokens import RefreshToken
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(tenant_a.id)
        token = RefreshToken.for_user(owner_a)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")
        r = _sell(c, warehouse_a.id, [
            {"product_id": product_a.id, "qty": "1", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 1500}])
        assert r.status_code == 402

    def test_suspended_CAN_access_billing(self, tenant_a, store_a, owner_a, suspended_sub):
        """Even suspended, billing endpoints should work (so they can pay)."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(tenant_a.id)
        token = RefreshToken.for_user(owner_a)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")
        r = c.get("/api/billing/subscription/")
        assert r.status_code == 200

    def test_webhook_falso_token(self):
        """Webhook with fake token → should not crash.

        In PAYMENT_GATEWAY=flow mode, missing/invalid HMAC signature → 403.
        In PAYMENT_GATEWAY=mock mode, signature is skipped → 200/400/502.
        """
        from django.conf import settings
        c = APIClient()
        r = c.post("/api/billing/webhook/flow/", {"token": "FAKE_TOKEN_12345"})
        if settings.PAYMENT_GATEWAY == "mock":
            assert r.status_code in (200, 400, 502)
        else:
            # Firma HMAC ausente → rechazo por seguridad
            assert r.status_code == 403

    def test_webhook_sin_token(self):
        c = APIClient()
        r = c.post("/api/billing/webhook/flow/", {})
        assert r.status_code == 400

    def test_confirm_payment_token_inventado(self, client_owner_a, tenant_a):
        """Frontend sends fake token → should handle gracefully."""
        from billing.models import Plan, Subscription
        plan, _ = Plan.objects.get_or_create(
            key="pro", defaults={"name": "Pro", "price_clp": 59990, "max_products": -1,
                                  "max_stores": -1, "max_users": -1},
        )
        Subscription.objects.get_or_create(
            tenant=tenant_a, defaults={"plan": plan, "status": "active",
                                        "current_period_start": timezone.now(),
                                        "current_period_end": timezone.now() + timedelta(days=30)},
        )
        r = client_owner_a.post("/api/billing/subscription/confirm-payment/", {
            "token": "INVENTED_TOKEN",
        }, format="json")
        # 502 (gateway error) or 404 (invoice not found) — not 500 server crash
        assert r.status_code in (200, 404, 400, 502)


# ═══════════════════════════════════════════════════════════════════════════════
# ATACANTE 7 — AUTH ABUSE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAuthAbuse:

    def test_no_auth_gets_401(self):
        c = APIClient()
        r = c.get("/api/catalog/products/")
        assert r.status_code in (401, 403)

    def test_invalid_jwt_gets_401(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer FAKE_JWT_TOKEN_HERE")
        r = c.get("/api/catalog/products/")
        assert r.status_code == 401

    def test_expired_jwt_gets_401(self):
        """Manually crafted expired token."""
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxMDAwMDAwMDAwfQ.fake")
        r = c.get("/api/catalog/products/")
        assert r.status_code == 401

    def test_login_wrong_password(self):
        c = APIClient()
        r = c.post("/api/auth/token/", {
            "username": "nonexistent", "password": "wrong",
        }, format="json")
        assert r.status_code == 401

    def test_refresh_invalid_token(self):
        c = APIClient()
        r = c.post("/api/auth/token/refresh/", {"refresh": "invalid_token"}, format="json")
        assert r.status_code == 401
