"""
Tests de regresión para los 5 bugs encontrados en la auditoría E2E
del 28/04/26. Cada uno reproduce el escenario exacto que rompía.
"""
import pytest
from decimal import Decimal

from inventory.models import StockItem, StockMove
from sales.models import Sale, SalePayment


def _seed_stock(tenant, warehouse, product, qty, avg_cost):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={
            "on_hand": Decimal("0.000"),
            "avg_cost": Decimal("0.000"),
            "stock_value": Decimal("0.000"),
        },
    )
    si.on_hand = Decimal(str(qty))
    si.avg_cost = Decimal(str(avg_cost))
    si.stock_value = (si.on_hand * si.avg_cost).quantize(Decimal("0.001"))
    si.save()
    return si


def _basic_payload(warehouse_id, product_id, qty, unit_price):
    return {
        "warehouse_id": warehouse_id,
        "lines": [{
            "product_id": product_id,
            "qty": str(qty),
            "unit_price": str(unit_price),
        }],
    }


@pytest.mark.django_db
class TestCashOverpaymentClamp:
    """Cuando el cliente paga con vuelto, SalePayment.amount NO debe
    incluir el vuelto. Sin esto, expected_cash queda inflado y la caja
    siempre va a faltar la diferencia al cierre.
    """

    def test_cash_overpayment_clamped_to_grand_total(
        self, api_client, tenant, warehouse, product,
    ):
        """Sale total $9.800 + tip $200 = $10.000. Cliente paga $11.000
        cash. Backend debe registrar payment.amount=$10.000 (no $11.000)."""
        _seed_stock(tenant, warehouse, product, qty=Decimal("10"), avg_cost=Decimal("500"))
        payload = _basic_payload(warehouse.id, product.id, qty=1, unit_price=9800)
        payload["payments"] = [{"method": "cash", "amount": 11000}]
        payload["tip"] = "200"

        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data

        payments = list(SalePayment.objects.filter(sale_id=r.data["id"]))
        assert len(payments) == 1
        assert payments[0].amount == Decimal("10000.00"), \
            f"payment.amount deberia ser $10.000 (sin vuelto), no {payments[0].amount}"

    def test_split_with_overpayment_only_clamps_last(
        self, api_client, tenant, warehouse, product,
    ):
        """Sale $10.000. Pagan $5.000 cash + $7.000 debit (sobra $2.000).
        El ULTIMO payment se clampa a $5.000."""
        _seed_stock(tenant, warehouse, product, qty=Decimal("10"), avg_cost=Decimal("500"))
        payload = _basic_payload(warehouse.id, product.id, qty=1, unit_price=10000)
        payload["payments"] = [
            {"method": "cash", "amount": 5000},
            {"method": "debit", "amount": 7000},
        ]
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data

        payments = list(SalePayment.objects.filter(sale_id=r.data["id"]).order_by("id"))
        assert len(payments) == 2
        assert payments[0].method == "cash" and payments[0].amount == Decimal("5000.00")
        assert payments[1].method == "debit" and payments[1].amount == Decimal("5000.00")
        total = sum(p.amount for p in payments)
        assert total == Decimal("10000.00")

    def test_exact_payment_unchanged(self, api_client, tenant, warehouse, product):
        """Pago exacto: ningun clamp."""
        _seed_stock(tenant, warehouse, product, qty=Decimal("10"), avg_cost=Decimal("500"))
        payload = _basic_payload(warehouse.id, product.id, qty=1, unit_price=5000)
        payload["payments"] = [{"method": "cash", "amount": 5000}]
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data

        p = SalePayment.objects.get(sale_id=r.data["id"])
        assert p.amount == Decimal("5000.00")


@pytest.mark.django_db
class TestRecipeVoidReversesIngredients:
    """Anular venta de producto con receta debe reversar el stock de los
    INGREDIENTES (no del producto compuesto que no tiene stock real).
    Bug critico encontrado en auditoria E2E -- Marbrava cafeteria.
    """

    def test_void_recipe_sale_restores_ingredient_stock(
        self, api_client, tenant, store, warehouse,
    ):
        """Capuchino con receta de leche. Vendemos 1 capuchino -> stock
        de leche baja. Anulamos -> stock de leche debe volver."""
        from catalog.models import Product, Recipe, RecipeLine, Unit

        # Setup unidades
        lt = Unit.objects.create(tenant=tenant, code="L", name="Litro", family="VOLUME", is_base=True, conversion_factor=Decimal("1"))
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad", family="COUNT", is_base=True, conversion_factor=Decimal("1"))

        # Producto Capuchino (compuesto)
        capuchino = Product.objects.create(
            tenant=tenant, name="Capuchino", sku="CAP1", price=Decimal("3000"),
            unit_obj=un,
        )
        # Ingrediente leche (con stock)
        leche = Product.objects.create(
            tenant=tenant, name="Leche", sku="LECHE1", price=Decimal("0"),
            cost=Decimal("500"), unit_obj=lt,
        )
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=leche,
            on_hand=Decimal("10.000"), avg_cost=Decimal("500"),
            stock_value=Decimal("5000"),
        )

        # Receta: 1 capuchino = 0.150 L de leche
        recipe = Recipe.objects.create(tenant=tenant, product=capuchino, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=leche,
            qty=Decimal("0.150"), unit=lt,
        )

        # Vender 1 capuchino
        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": capuchino.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        # Stock de leche bajo 0.150 (10 -> 9.850)
        leche_si = StockItem.objects.get(product=leche, warehouse=warehouse)
        assert leche_si.on_hand == Decimal("9.850"), f"Got {leche_si.on_hand}"

        # Anular
        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200, rv.data

        # Stock de leche debe volver a 10.000
        leche_si.refresh_from_db()
        assert leche_si.on_hand == Decimal("10.000"), \
            f"BUG: stock leche deberia volver a 10, quedo en {leche_si.on_hand}"

        # NO phantom stock del Capuchino
        cap_si = StockItem.objects.filter(product=capuchino, warehouse=warehouse).first()
        if cap_si:
            assert cap_si.on_hand == Decimal("0.000"), \
                f"BUG: capuchino no deberia tener stock, tiene {cap_si.on_hand}"

        # StockMove SALE_VOID para la leche
        leche_void = StockMove.objects.filter(
            ref_type="SALE_VOID", ref_id=sale_id, product=leche,
        ).first()
        assert leche_void is not None, "Falta StockMove SALE_VOID para la leche"
        assert leche_void.qty == Decimal("0.150")


@pytest.mark.django_db
class TestPromotionEnforcement:
    """Si hay una promo activa pero el frontend manda unit_price
    > promo_price (cache stale), el backend debe forzar el promo_price.
    """

    def test_promotion_overrides_stale_unit_price(
        self, api_client, tenant, warehouse, product,
    ):
        from promotions.models import Promotion, PromotionProduct
        from django.utils import timezone
        from datetime import timedelta

        product.price = Decimal("1000")
        product.save()
        _seed_stock(tenant, warehouse, product, qty=Decimal("10"), avg_cost=Decimal("300"))

        now = timezone.now()
        promo = Promotion.objects.create(
            tenant=tenant, name="Test 30 off",
            discount_type="pct",  # 'pct' o 'fixed_price' segun modelo
            discount_value=Decimal("30"),
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
            is_active=True,
        )
        PromotionProduct.objects.create(promotion=promo, product=product)

        # Cliente manda unit_price = $1000 (precio sin promo)
        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": product.id, "qty": "1", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 700}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data

        sale = Sale.objects.get(pk=r.data["id"])
        assert sale.total == Decimal("700"), \
            f"BUG: promo no se aplico. Total quedo en {sale.total}"
