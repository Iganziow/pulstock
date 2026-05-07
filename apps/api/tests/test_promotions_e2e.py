"""
Tests E2E del módulo de promociones — payload EXACTO del frontend.

Hay test_promotions.py con 16 tests pero no cubren el payload real
(product_items con override) ni edge cases del PATCH.

Mario reportó (07/05/26) bug en discount_type ("percentage" rechazado).
Este archivo audita el resto del módulo buscando bugs similares antes
de que Mario los encuentre en producción.
"""
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from core.models import User, Tenant
from stores.models import Store
from promotions.models import Promotion, PromotionProduct


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def two_products(tenant):
    p1 = Product.objects.create(tenant=tenant, name="Latte", price=Decimal("3000"), is_active=True)
    p2 = Product.objects.create(tenant=tenant, name="Brownie", price=Decimal("1500"), is_active=True)
    return [p1, p2]


@pytest.fixture
def now_dt():
    return timezone.now()


def _frontend_payload(products, *, discount_type="pct", discount_value="30",
                       start=None, end=None, overrides=None, name="Test promo"):
    """Construye el body EXACTO que manda el frontend (PromotionFormModal +
    page.tsx → handleSave). Replicar bugs del front empieza acá."""
    start = start or timezone.now()
    end = end or (start + timedelta(days=7))
    overrides = overrides or {}

    return {
        "name": name,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "product_items": [
            {
                "product_id": p.id,
                "override_discount_value": overrides.get(p.id),
            }
            for p in products
        ],
    }


# ── CREATE: payload tal cual lo manda el frontend ─────────────────────────


@pytest.mark.django_db
class TestCreateWithFrontendPayload:
    """El test que tendría que haber existido desde el día 1."""

    def test_create_pct_promo_with_real_frontend_payload(
        self, api_client, two_products, owner
    ):
        """Esto es lo que MARIO mandó desde el formulario. discount_type='pct',
        product_items con override null. Tiene que pasar."""
        payload = _frontend_payload(two_products, discount_type="pct", discount_value="30")
        resp = api_client.post("/api/promotions/", payload, format="json")

        assert resp.status_code == 201, (
            f"Create con payload frontend falló con status {resp.status_code}: {resp.content}"
        )
        data = resp.json()
        assert data["discount_type"] == "pct"
        assert Decimal(data["discount_value"]) == Decimal("30")
        assert len(data["items"]) == 2

    def test_create_fixed_promo_with_real_frontend_payload(
        self, api_client, two_products
    ):
        """Misma cosa pero precio fijo."""
        payload = _frontend_payload(two_products, discount_type="fixed_price",
                                     discount_value="2500")
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 201, resp.content
        assert resp.json()["discount_type"] == "fixed_price"

    def test_legacy_invalid_discount_type_rejected(
        self, api_client, two_products
    ):
        """Si alguien todavía manda 'percentage' (fix incompleto), tiene
        que devolver 400 limpio."""
        payload = _frontend_payload(two_products)
        payload["discount_type"] = "percentage"
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400
        assert "discount_type" in str(resp.content)

    def test_create_with_overrides_per_product(
        self, api_client, two_products
    ):
        """El frontend permite override_discount_value por producto.
        Verifica que el backend lo guarde."""
        p1, p2 = two_products
        payload = _frontend_payload(
            two_products, discount_type="pct", discount_value="20",
            overrides={p1.id: "40"},  # Latte 40%, Brownie usa el default 20%
        )
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 201, resp.content

        promo = Promotion.objects.get(id=resp.json()["id"])
        items = {pp.product_id: pp for pp in promo.items.all()}
        assert items[p1.id].override_discount_value == Decimal("40")
        assert items[p2.id].override_discount_value is None


# ── CREATE: validaciones ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCreateValidations:

    def test_pct_value_over_100_rejected(self, api_client, two_products):
        payload = _frontend_payload(two_products, discount_type="pct",
                                     discount_value="150")
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_pct_value_zero_rejected(self, api_client, two_products):
        payload = _frontend_payload(two_products, discount_type="pct",
                                     discount_value="0")
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_pct_value_negative_rejected(self, api_client, two_products):
        payload = _frontend_payload(two_products, discount_type="pct",
                                     discount_value="-10")
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_fixed_value_zero_rejected(self, api_client, two_products):
        payload = _frontend_payload(two_products, discount_type="fixed_price",
                                     discount_value="0")
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_end_before_start_rejected(self, api_client, two_products, now_dt):
        payload = _frontend_payload(
            two_products,
            start=now_dt,
            end=now_dt - timedelta(days=1),
        )
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_no_products_rejected(self, api_client):
        payload = _frontend_payload([])  # product_items: []
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400

    def test_inactive_product_rejected(self, api_client, tenant):
        """Si el producto está soft-deleted, no se puede agregar a promo."""
        p = Product.objects.create(
            tenant=tenant, name="Producto inactivo",
            price=Decimal("1000"), is_active=False,
        )
        payload = _frontend_payload([p])
        resp = api_client.post("/api/promotions/", payload, format="json")
        assert resp.status_code == 400


# ── PATCH: edge cases que test_promotions.py NO cubre ──────────────────────


@pytest.mark.django_db
class TestPatchEdgeCases:
    """Bugs sospechados en views.py:130-156 — los setattr blind no
    revalidan choices ni reglas de negocio."""

    @pytest.fixture
    def promo(self, tenant, two_products):
        promo = Promotion.objects.create(
            tenant=tenant, name="Promo original",
            discount_type="pct", discount_value=Decimal("20"),
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=7),
        )
        for p in two_products:
            PromotionProduct.objects.create(promotion=promo, product=p)
        return promo

    def test_patch_invalid_discount_type_rejected(self, api_client, promo):
        """BUG SOSPECHADO: PATCH hace setattr blind sin validar choices.
        Si pasa, queda en DB con valor inválido."""
        resp = api_client.patch(
            f"/api/promotions/{promo.id}/",
            {"discount_type": "invalid_type"}, format="json",
        )
        # Si esto devuelve 200, hay BUG.
        promo.refresh_from_db()
        if resp.status_code == 200 and promo.discount_type == "invalid_type":
            pytest.fail(
                "BUG: PATCH /api/promotions/<id>/ aceptó discount_type='invalid_type'. "
                "El backend hace setattr blind en views.py:139 sin validar choices. "
                "Fix: agregar choice validator antes del setattr."
            )

    def test_patch_pct_value_over_100_rejected(self, api_client, promo):
        """Si la promo es pct y le mandamos discount_value=150, debería
        rechazar. Pero el PATCH solo valida >0, no <=100."""
        resp = api_client.patch(
            f"/api/promotions/{promo.id}/",
            {"discount_value": "150"}, format="json",
        )
        promo.refresh_from_db()
        if resp.status_code == 200 and promo.discount_value == Decimal("150"):
            pytest.fail(
                "BUG: PATCH aceptó discount_value=150 en una promo pct. "
                "El frontend bloquea pero el backend no — consistencia rota."
            )

    def test_patch_end_before_start_rejected(self, api_client, promo):
        """Si actualizamos end_date a antes del start_date, debería rechazar.
        Pero el PATCH no re-valida esa relación."""
        new_end = promo.start_date - timedelta(days=1)
        resp = api_client.patch(
            f"/api/promotions/{promo.id}/",
            {"end_date": new_end.isoformat()}, format="json",
        )
        promo.refresh_from_db()
        if resp.status_code == 200 and promo.end_date < promo.start_date:
            pytest.fail(
                "BUG: PATCH aceptó end_date < start_date. La promo nunca "
                "estaría activa pero ocupa espacio en la lista."
            )


# ── Conflictos de promociones ──────────────────────────────────────────────


@pytest.mark.django_db
class TestConflictDetection:
    """El frontend usa /api/promotions/check-conflicts/ para avisar al
    dueño que ya hay una promo activa para el mismo producto."""

    def test_check_conflicts_finds_overlap(self, api_client, tenant, two_products):
        """Crear una promo, después chequear si una nueva con misma fecha
        choca → debería devolver el conflicto."""
        existing = Promotion.objects.create(
            tenant=tenant, name="Existente",
            discount_type="pct", discount_value=Decimal("20"),
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=10),
        )
        for p in two_products:
            PromotionProduct.objects.create(promotion=existing, product=p)

        resp = api_client.post("/api/promotions/check-conflicts/", {
            "product_ids": [two_products[0].id],
            "start_date": (timezone.now() + timedelta(days=2)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=5)).isoformat(),
        }, format="json")

        assert resp.status_code == 200
        conflicts = resp.json()["conflicts"]
        assert len(conflicts) == 1
        assert conflicts[0]["conflicting_promotion_id"] == existing.id

    def test_check_conflicts_excludes_self_when_editing(
        self, api_client, tenant, two_products
    ):
        """Al editar una promo, el check no debe marcarla como conflicto
        de sí misma (parámetro exclude_promotion_id)."""
        existing = Promotion.objects.create(
            tenant=tenant, name="Self",
            discount_type="pct", discount_value=Decimal("20"),
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=10),
        )
        PromotionProduct.objects.create(promotion=existing, product=two_products[0])

        resp = api_client.post("/api/promotions/check-conflicts/", {
            "product_ids": [two_products[0].id],
            "start_date": timezone.now().isoformat(),
            "end_date": (timezone.now() + timedelta(days=10)).isoformat(),
            "exclude_promotion_id": existing.id,
        }, format="json")

        assert resp.status_code == 200
        assert len(resp.json()["conflicts"]) == 0


# ── Flujo de venta con promo activa ────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestSaleAppliesPromo:
    """El test crítico: Mario crea una promo y después el cajero vende
    el producto. ¿Se aplica el precio promocional?"""

    def test_active_promo_endpoint_returns_promo_for_product(
        self, api_client, tenant, two_products
    ):
        """GET /api/promotions/active-for-products/?product_ids=1,2 →
        el POS lo usa para auto-aplicar el descuento."""
        promo = Promotion.objects.create(
            tenant=tenant, name="30% off",
            discount_type="pct", discount_value=Decimal("30"),
            start_date=timezone.now() - timedelta(hours=1),  # ya empezada
            end_date=timezone.now() + timedelta(days=7),
        )
        PromotionProduct.objects.create(promotion=promo, product=two_products[0])

        ids_str = ",".join(str(p.id) for p in two_products)
        resp = api_client.get(f"/api/promotions/active-for-products/?product_ids={ids_str}")
        assert resp.status_code == 200

        results = resp.json()["results"]
        assert len(results) == 1, (
            f"Esperaba 1 promo activa para Latte. Got: {results}"
        )
        r = results[0]
        assert r["product_id"] == two_products[0].id
        assert r["discount_type"] == "pct"
        # Latte $3000 - 30% = $2100
        assert Decimal(r["promo_price"]) == Decimal("2100")

    def test_inactive_promo_not_returned(
        self, api_client, tenant, two_products
    ):
        """Una promo con is_active=False NO debe aparecer en active-for-products."""
        promo = Promotion.objects.create(
            tenant=tenant, name="Desactivada",
            discount_type="pct", discount_value=Decimal("50"),
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(days=7),
            is_active=False,  # ← desactivada
        )
        PromotionProduct.objects.create(promotion=promo, product=two_products[0])

        resp = api_client.get(
            f"/api/promotions/active-for-products/?product_ids={two_products[0].id}"
        )
        assert resp.json()["results"] == []

    def test_future_promo_not_returned(
        self, api_client, tenant, two_products
    ):
        """Promo programada para el futuro NO se aplica todavía."""
        promo = Promotion.objects.create(
            tenant=tenant, name="Futura",
            discount_type="pct", discount_value=Decimal("30"),
            start_date=timezone.now() + timedelta(days=1),  # ← mañana
            end_date=timezone.now() + timedelta(days=7),
        )
        PromotionProduct.objects.create(promotion=promo, product=two_products[0])

        resp = api_client.get(
            f"/api/promotions/active-for-products/?product_ids={two_products[0].id}"
        )
        assert resp.json()["results"] == []

    def test_expired_promo_not_returned(
        self, api_client, tenant, two_products
    ):
        """Promo cuya end_date ya pasó NO se aplica."""
        promo = Promotion.objects.create(
            tenant=tenant, name="Expirada",
            discount_type="pct", discount_value=Decimal("30"),
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=1),  # ← ayer
        )
        PromotionProduct.objects.create(promotion=promo, product=two_products[0])

        resp = api_client.get(
            f"/api/promotions/active-for-products/?product_ids={two_products[0].id}"
        )
        assert resp.json()["results"] == []
