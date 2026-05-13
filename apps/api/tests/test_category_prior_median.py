"""
Tests del cambio (13/05/26) en compute_category_profiles:
PROMEDIO → MEDIANA de productos con consumo > 0.

Razón: el promedio se rompe con outliers. Si una categoría tiene 1
producto popular (vende 100/día) y 9 lentos (venden 0-1/día), el
promedio da ~11/día y predice 11 para los 9 lentos → sobre-predicción
masiva. La mediana ignora el outlier y predice 0.5 para los lentos.

Bug detectado por Mario el 13/05/26 — WAPE de category_prior = 552%
en producción.
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.core.management import call_command

from catalog.models import Product, Category
from core.models import Warehouse
from forecast.models import DailySales, CategoryDemandProfile
from forecast.management.commands.compute_category_profiles import (
    category_prior_estimator,
)


# ── Tests unitarios del helper ─────────────────────────────────────────────


class TestCategoryPriorEstimator:
    """La política nueva: mediana de productos con consumo > 0."""

    def test_outlier_does_not_inflate(self):
        """Caso real de Mario: 1 producto popular + 9 lentos.
        Promedio: (100 + 5*9) / 10 = 14.5 → predicción inflada
        Mediana de los 10 valores: 0.5 → predicción realista
        Mediana sin ceros (nuestro caso): igual"""
        per_product = [100, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        result = category_prior_estimator(per_product)
        assert result == pytest.approx(0.5, abs=0.001), (
            f"Mediana esperaba 0.5, obtuvo {result}. "
            f"El outlier 100 NO debe afectar el resultado."
        )

    def test_excludes_zero_products(self):
        """Productos que NUNCA vendieron son ruido — no representan el
        nivel típico de la categoría. Se excluyen ANTES de calcular
        mediana.

        Caso: [0, 0, 0, 0, 5, 10, 100]
        Mediana cruda: 0 (mediana del array completo)
        Mediana sin ceros: mediana de [5, 10, 100] = 10 ← lo que queremos
        """
        per_product = [0, 0, 0, 0, 5, 10, 100]
        result = category_prior_estimator(per_product)
        assert result == pytest.approx(10.0, abs=0.001), (
            f"Esperaba mediana sin ceros = 10, obtuvo {result}. "
            f"Si da 0, la función está incluyendo ceros."
        )

    def test_all_zeros_returns_zero(self):
        """Categoría sin ventas: predecir 0 es razonable (categoría
        inactiva — quizás productos descontinuados)."""
        per_product = [0, 0, 0, 0]
        assert category_prior_estimator(per_product) == 0.0

    def test_empty_list_returns_zero(self):
        assert category_prior_estimator([]) == 0.0

    def test_single_product(self):
        """1 solo producto en categoría: mediana = ese valor."""
        assert category_prior_estimator([7.5]) == 7.5

    def test_two_products_different(self):
        """Mediana de 2 elementos = promedio de los 2 (siempre que
        ninguno sea 0)."""
        result = category_prior_estimator([4, 10])
        assert result == pytest.approx(7.0, abs=0.001)

    def test_compared_with_old_mean_behavior(self):
        """Caso real de Postres en Marbrava (3.860× dispersión):
        - 1 postre vende 38/día (Pie de limón)
        - 22 venden 0,01/día
        Promedio (viejo): (38 + 22*0.01) / 23 = 1.66/día
          → predecía 1.66 para postres lentos = 166× su consumo real
        Mediana (nuevo, con ceros excluidos): 0.01
          → predecía 0.01 ≈ realidad ✓"""
        per_product = [38.0] + [0.01] * 22
        old_mean = sum(per_product) / len(per_product)
        new_median = category_prior_estimator(per_product)
        assert old_mean > 1.5, "Confirma que el promedio quedaba inflado"
        assert new_median == pytest.approx(0.01, abs=0.001), (
            f"La mediana debe quedar cerca del valor típico (0.01), "
            f"no del outlier 38. Obtuvo {new_median}."
        )


# ── Test de integración con el comando ─────────────────────────────────────


@pytest.mark.django_db
class TestComputeCategoryProfilesUsesMedian:

    def test_command_uses_median_in_db(self, tenant, store):
        """End-to-end: corremos `compute_category_profiles` y verificamos
        que el avg_daily_demand guardado en DB es la mediana, no el
        promedio."""
        from datetime import timedelta as _td
        warehouse = Warehouse.objects.create(
            tenant=tenant, store=store, name="W-cat-test",
        )
        cat = Category.objects.create(tenant=tenant, name="Postres test")

        # 1 producto popular, 4 lentos
        p_popular = Product.objects.create(
            tenant=tenant, name="Pie estrella", price=Decimal("3000"),
            category=cat, is_active=True,
        )
        slow_products = []
        for i in range(4):
            p = Product.objects.create(
                tenant=tenant, name=f"Postre lento {i}", price=Decimal("1000"),
                category=cat, is_active=True,
            )
            slow_products.append(p)

        # Sembrar DailySales últimos 14 días
        # Pie estrella: 38/día
        # Lentos: 0.5/día
        today = date.today()
        for d_offset in range(14):
            d = today - _td(days=d_offset + 1)
            DailySales.objects.create(
                tenant=tenant, product=p_popular, warehouse=warehouse,
                date=d, qty_sold=Decimal("38.000"),
            )
            for sp in slow_products:
                DailySales.objects.create(
                    tenant=tenant, product=sp, warehouse=warehouse,
                    date=d, qty_sold=Decimal("0.500"),
                )

        call_command("compute_category_profiles", "--days", "30", "--tenant", tenant.id)

        prof = CategoryDemandProfile.objects.get(
            tenant=tenant, category=cat, warehouse=warehouse,
        )
        # Mediana de [38, 0.5, 0.5, 0.5, 0.5] = 0.5
        # Promedio (viejo) hubiera dado: (38 + 4*0.5) / 5 = 8.0
        assert prof.avg_daily_demand == Decimal("0.500"), (
            f"Esperaba 0.500 (mediana), obtuvo {prof.avg_daily_demand}. "
            f"Si da 8.0 o cerca, todavía está usando promedio."
        )
        assert prof.product_count == 5
