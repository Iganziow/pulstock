# -*- coding: utf-8 -*-
"""
tests/test_correo_stock_bajo.py — el correo tiene que decir QUE producto.

Visto en produccion el 03/09/26: el correo de stock bajo listaba

    Bodega Principal                    Sin stock    sin stock
    Bodega Principal                    Sin stock    sin stock

cuatro veces, sin el nombre del producto. `render_low_stock_v2` armaba cada
fila con la clave `product_name` y la plantilla lee `{{ it.name }}`: Django
resuelve una clave inexistente como cadena vacia y no avisa. El texto plano
si mostraba los nombres (usa las alertas originales), asi que el defecto
solo aparecia en HTML -- que es lo que abre casi todo el mundo.

Es una de las dos alertas que la landing promete.
"""
import pytest

from billing.email_renderers import render_low_stock_v2


def _alerta(nombre, on_hand=0, razon="Sin stock", dias=None):
    return {
        "product_name": nombre, "sku": "SKU-1", "warehouse": "Bodega Principal",
        "on_hand": on_hand, "avg_daily": 0.4, "days_left": dias,
        "reason_text": razon,
    }


@pytest.mark.django_db
class TestElCorreoNombraLosProductos:
    def test_el_html_trae_el_nombre_de_cada_producto(self, tenant):
        criticos = [_alerta("Leche entera"), _alerta("Cafe tolva caturra")]
        bajos = [_alerta("Chocolate Premium", on_hand=5,
                         razon="Te alcanza para 8.4 dias", dias=8.4)]

        _subject, _plain, html = render_low_stock_v2(tenant, criticos, bajos)

        for nombre in ("Leche entera", "Cafe tolva caturra", "Chocolate Premium"):
            assert nombre in html, (
                "el HTML del correo no nombra '%s': el destinatario ve "
                "'Sin stock' sin saber de que producto" % nombre
            )

    def test_el_texto_plano_tambien(self, tenant):
        """La otra mitad: ya funcionaba y no puede romperse al arreglar el HTML."""
        _s, plain, _h = render_low_stock_v2(tenant, [_alerta("Queso")], [])
        assert "Queso" in plain

    def test_la_bodega_sigue_apareciendo(self, tenant):
        """El nombre no puede haber reemplazado a la bodega."""
        _s, _p, html = render_low_stock_v2(tenant, [_alerta("Te")], [])
        assert "Bodega Principal" in html

    def test_sin_criticos_no_revienta(self, tenant):
        _s, _p, html = render_low_stock_v2(tenant, [], [_alerta("Cacao", on_hand=2)])
        assert "Cacao" in html
