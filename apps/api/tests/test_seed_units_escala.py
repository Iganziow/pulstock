"""
tests/test_seed_units_escala.py — sembrar unidades sobre otra convención.

Los factores de `seed_units` están expresados contra SU base: gramo para masa,
mililitro para volumen. Si el tenant ya tiene unidades con otra convención
—kilo como base, con GR=0.001— insertar el factor tal cual deja conversiones
erradas por 1000×.

No es teórico: pasó el 23-ago-2026 al sembrar las unidades de restaurante en
Marbrava, que tenía Litro como base. Se creó TAZA con factor 250 (correcto si
la base fuera ML) y `1 taza` daba **250.000 ml**. Nadie alcanzó a usarla, pero
una receta con esa unidad destruye stock, costo y forecast de una sola vez.
"""
from decimal import Decimal

import pytest

from catalog.models import Unit
from catalog.management.commands.seed_units import seed_units_for_tenant
from catalog.unit_conversion import convert_qty

D = Decimal


def _unidad(tenant, code, name, family, factor, base=None):
    return Unit.objects.create(
        tenant=tenant, code=code, name=name, family=family,
        conversion_factor=D(factor), base_unit=base, is_active=True,
    )


@pytest.mark.django_db
class TestSembrarSobreOtraConvencion:
    def test_respeta_la_base_que_el_tenant_ya_tenia(self, tenant):
        """EL BUG. El tenant usa Litro como base; la semilla asume Mililitro."""
        ml = _unidad(tenant, "ML", "Mililitro", "VOLUME", "0.001")
        _unidad(tenant, "L", "Litro", "VOLUME", "1")

        seed_units_for_tenant(tenant, business_type="restaurant")

        taza = Unit.objects.get(tenant=tenant, code="TAZA")
        resultado = float(convert_qty(D("1"), taza, ml))
        assert abs(resultado - 250) < 0.01, (
            f"1 taza dio {resultado} ml en vez de 250 — la semilla ignoró la "
            f"convención del tenant y el factor quedó 1000x"
        )

    def test_lo_mismo_para_masa(self, tenant):
        gr = _unidad(tenant, "GR", "Gramo", "MASS", "0.001")
        _unidad(tenant, "KG", "Kilogramo", "MASS", "1")

        seed_units_for_tenant(tenant, business_type="restaurant")

        oz = Unit.objects.get(tenant=tenant, code="OZ")
        resultado = float(convert_qty(D("1"), oz, gr))
        assert abs(resultado - 28.35) < 0.1, (
            f"1 onza dio {resultado} gramos en vez de 28,35"
        )

    def test_un_tenant_nuevo_se_siembra_igual_que_siempre(self, tenant):
        """Sin unidades previas la escala es 1: no cambia el comportamiento
        histórico."""
        assert Unit.objects.filter(tenant=tenant).count() == 0

        seed_units_for_tenant(tenant, business_type="restaurant")

        gr = Unit.objects.get(tenant=tenant, code="GR")
        kg = Unit.objects.get(tenant=tenant, code="KG")
        assert gr.conversion_factor == D("1")
        assert kg.conversion_factor == D("1000")
        assert abs(float(convert_qty(D("1"), kg, gr)) - 1000) < 0.01

    def test_las_conversiones_cierran_entre_si(self, tenant):
        """La prueba que importa: ida y vuelta sin perder nada."""
        _unidad(tenant, "ML", "Mililitro", "VOLUME", "0.001")
        _unidad(tenant, "L", "Litro", "VOLUME", "1")
        seed_units_for_tenant(tenant, business_type="restaurant")

        ml = Unit.objects.get(tenant=tenant, code="ML")
        taza = Unit.objects.get(tenant=tenant, code="TAZA")
        cuch = Unit.objects.get(tenant=tenant, code="CUCH")

        # Una taza son 250 ml; una cucharada, 15. Entonces una taza tiene
        # 250/15 cucharadas.
        assert abs(float(convert_qty(D("1"), taza, cuch)) - (250 / 15)) < 0.01
        # Y volver deja el mismo número.
        ida = convert_qty(D("2"), taza, ml)
        vuelta = convert_qty(ida, ml, taza)
        assert abs(float(vuelta) - 2) < 0.001

    def test_no_crea_una_unidad_que_ya_existe_con_otro_codigo(self, tenant):
        """El tenant tenía 'L' para litro; la semilla trae 'LT'. Duplicar el
        litro con distinto factor es exactamente lo que hizo que 1 LT diera un
        millón de mililitros."""
        _unidad(tenant, "ML", "Mililitro", "VOLUME", "0.001")
        _unidad(tenant, "L", "Litro", "VOLUME", "1")

        seed_units_for_tenant(tenant, business_type="restaurant")

        litros = Unit.objects.filter(tenant=tenant, name__iexact="Litro")
        factores = {str(u.conversion_factor) for u in litros}
        assert len(factores) <= 1, (
            f"hay litros con factores distintos: {factores} — una receta puede "
            f"tomar el equivocado"
        )
