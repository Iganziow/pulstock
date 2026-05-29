"""
Tests F1.1 + F1.2 — Backfill de quiebres / detección de stockout (Mario 29/05/26).

F1.1: command backfill_stockout_detection reconstruye closing_stock desde
      StockMove (backward desde on_hand) y marca is_stockout retroactivo,
      con criterio conservador que evita falsos positivos.
F1.2: aggregate_daily_sales usa el qty_sold REAL + criterio opening>0.
"""
from datetime import timedelta, date as date_cls
from decimal import Decimal

import pytest
from django.utils import timezone
from django.core.management import call_command

from catalog.models import Product
from inventory.models import StockItem, StockMove
from forecast.models import DailySales


def _product(tenant, name="Café tolva"):
    return Product.objects.create(tenant=tenant, name=name, price=Decimal("1000"), is_active=True)


def _move(tenant, warehouse, product, move_type, qty, days_ago):
    return StockMove.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        move_type=move_type, qty=Decimal(str(qty)),
        created_at=timezone.now() - timedelta(days=days_ago),
    )


def _daily(tenant, warehouse, product, days_ago, qty_sold="0", qty_received="0", qty_lost="0", forecast_only=False):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        date=date_cls.today() - timedelta(days=days_ago),
        qty_sold=Decimal(str(qty_sold)), qty_received=Decimal(str(qty_received)),
        qty_lost=Decimal(str(qty_lost)), forecast_only=forecast_only,
    )


@pytest.mark.django_db
class TestBackfillStockout:
    def _scenario(self, tenant, warehouse, product):
        """Stock vivo = 5. Movimientos que hacen que D-2 cierre en 0 (se agotó):
            D-3: IN 10
            D-2: OUT 10  (vendió todo → cerró en 0)
            D-1: IN 5    (repuso)
        Reconstrucción backward desde on_hand=5:
            closing(hoy)=5, closing(D-1)=5, closing(D-2)=0, closing(D-3)=10
        """
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                                 on_hand=Decimal("5"), avg_cost=Decimal("500"))
        _move(tenant, warehouse, product, StockMove.IN, 10, days_ago=3)
        _move(tenant, warehouse, product, StockMove.OUT, 10, days_ago=2)
        _move(tenant, warehouse, product, StockMove.IN, 5, days_ago=1)

    def test_reconstructs_closing_and_marks_stockout(self, tenant, warehouse, product):
        self._scenario(tenant, warehouse, product)
        # D-2: vendió 10 y cerró en 0 → stockout (se agotó habiendo tenido stock)
        d2 = _daily(tenant, warehouse, product, days_ago=2, qty_sold="10")
        # D-3: cerró en 10 → NO stockout
        d3 = _daily(tenant, warehouse, product, days_ago=3, qty_sold="0", qty_received="10")

        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")

        d2.refresh_from_db(); d3.refresh_from_db()
        assert d2.closing_stock == Decimal("0.000"), f"D-2 closing={d2.closing_stock}"
        assert d2.is_stockout is True, "D-2 se agotó → stockout"
        assert d3.closing_stock == Decimal("10.000"), f"D-3 closing={d3.closing_stock}"
        assert d3.is_stockout is False, "D-3 tenía stock → no stockout"

    def test_no_false_positive_for_unstocked_lowrotation(self, tenant, warehouse, product):
        """Producto sin reponer: cerró en 0 PERO abrió en 0 y no recibió ni
        vendió (baja rotación) → NO se marca stockout (evita inflar demanda)."""
        # on_hand=0, sin movimientos → todos los días cierran en 0
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                                 on_hand=Decimal("0"), avg_cost=Decimal("500"))
        d = _daily(tenant, warehouse, product, days_ago=2, qty_sold="0")

        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")
        d.refresh_from_db()
        assert d.closing_stock == Decimal("0.000")
        assert d.is_stockout is False, "sin stock + sin demanda + sin recepción → no es stockout"

    def test_respects_forecast_only(self, tenant, warehouse, product):
        """Filas forecast_only=True (histórico Fudo) NUNCA se tocan."""
        self._scenario(tenant, warehouse, product)
        fo = _daily(tenant, warehouse, product, days_ago=2, qty_sold="10", forecast_only=True)
        assert fo.closing_stock is None

        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")
        fo.refresh_from_db()
        assert fo.closing_stock is None, "forecast_only no debe tocarse"
        assert fo.is_stockout is False

    def test_dry_run_does_not_write(self, tenant, warehouse, product):
        self._scenario(tenant, warehouse, product)
        d2 = _daily(tenant, warehouse, product, days_ago=2, qty_sold="10")

        # Sin --apply → dry-run
        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10")
        d2.refresh_from_db()
        assert d2.closing_stock is None, "dry-run no debe escribir"
        assert d2.is_stockout is False

    def test_idempotent(self, tenant, warehouse, product):
        self._scenario(tenant, warehouse, product)
        d2 = _daily(tenant, warehouse, product, days_ago=2, qty_sold="10")

        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")
        d2.refresh_from_db()
        first = (d2.closing_stock, d2.is_stockout)
        call_command("backfill_stockout_detection", "--tenant", str(tenant.id), "--days", "10", "--apply")
        d2.refresh_from_db()
        assert (d2.closing_stock, d2.is_stockout) == first, "segunda corrida da el mismo resultado"


@pytest.mark.django_db
class TestStockoutInterpolationEffect:
    """El día marcado is_stockout con qty_sold=0 debe interpolarse en
    clean_series (no aprender el 0 censurado)."""

    def test_clean_series_imputes_marked_stockout_day(self, tenant, warehouse, product):
        from forecast.engine.utils import clean_series
        base = date_cls.today() - timedelta(days=20)
        # Serie: vende ~5/día los lunes; un lunes se quiebra (qty=0, stockout)
        series = []
        stockout_dates = set()
        for i in range(20):
            d = base + timedelta(days=i)
            if d.weekday() == 0 and i > 7:  # un lunes tardío = quiebre
                series.append((d, 0.0))
                stockout_dates.add(d)
            elif d.weekday() == 0:
                series.append((d, 5.0))  # lunes normales venden 5
            else:
                series.append((d, 2.0))
        cleaned = clean_series(series, stockout_dates)
        # clean_series devuelve (date, qty, weight). El lunes en stockout no
        # debe quedar en 0 (se imputa con avg del día-de-semana).
        cleaned_map = {row[0]: row[1] for row in cleaned}
        for d in stockout_dates:
            assert cleaned_map[d] > 0, f"día stockout {d} debe imputarse, no quedar en 0"
