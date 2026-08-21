"""
tests/test_concurrencia_mesas.py — 12 garzones sobre la misma mesa.

Corre contra PostgreSQL real (no SQLite): SQLite serializa toda la base y
esconde justo las carreras que queremos ver.

Lo que se prueba:
  1. Garzones distintos agregando a la MISMA mesa a la vez → no se pierde
     ninguna comanda. Agregar líneas es un append, no un update, así que
     esto debe funcionar por naturaleza; el test lo fija para que nadie
     introduzca un total guardado más adelante sin darse cuenta.
  2. El mismo batch reintentado dos veces en paralelo (WiFi inestable) →
     NO debe duplicar. La idempotencia hoy es check-then-insert sin
     constraint único, así que esta es la carrera real.
"""
import threading
import uuid

import pytest
from django.db import connection, connections

from catalog.models import Product
from tables.models import OpenOrder, OpenOrderLine, Table


# Sin PostgreSQL esto no prueba nada: SQLite serializa la base entera, asi que
# los hilos chocan con "database is locked" en vez de mostrar la carrera. Peor
# aun, `select_for_update` es un no-op en SQLite — el arreglo que verificamos
# aca seria invisible. Correr con:
#   DATABASE_URL="postgres://pulstock:testpass@localhost:55433/pulstock_test" pytest
pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="concurrencia real: requiere PostgreSQL (SQLite serializa y "
               "convierte select_for_update en un no-op)",
    ),
]


@pytest.fixture
def mesa(db, tenant, store):
    return Table.objects.create(tenant=tenant, store=store, name="Mesa 5", capacity=4)


@pytest.fixture
def orden(db, tenant, store, warehouse, mesa, owner):
    return OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=mesa, opened_by=owner, status=OpenOrder.STATUS_OPEN,
    )


@pytest.fixture
def productos(db, tenant, category):
    return [
        Product.objects.create(
            tenant=tenant, name=f"Producto {i}", sku=f"P-{i}",
            category=category, price=1000,
        )
        for i in range(12)
    ]


def _correr_en_paralelo(fn, n):
    """Lanza n hilos que arrancan lo más cerca posible del mismo instante."""
    barrera = threading.Barrier(n)
    errores = []

    def worker(i):
        try:
            barrera.wait()
            fn(i)
        except Exception as exc:          # pragma: no cover - diagnóstico
            errores.append(repr(exc))
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    return errores


class TestDoceGarzonesMismaMesa:
    def test_doce_garzones_agregan_a_la_vez_y_no_se_pierde_nada(
        self, orden, productos, tenant, owner,
    ):
        """El caso del turno lleno: 12 garzones comandando la misma mesa."""
        usuario = owner

        def agregar(i):
            OpenOrderLine.objects.create(
                tenant=tenant, order=orden, product=productos[i],
                qty=1, unit_price=1000, added_by=usuario,
            )

        errores = _correr_en_paralelo(agregar, 12)
        assert errores == [], f"hubo errores: {errores}"

        lineas = OpenOrderLine.objects.filter(order=orden)
        assert lineas.count() == 12, (
            "cada comanda tiene que llegar: agregar es un append, "
            "no puede perderse ninguna"
        )
        # Y cada producto aparece exactamente una vez.
        assert len({l.product_id for l in lineas}) == 12

    def test_el_total_se_calcula_de_las_lineas_no_se_acumula(
        self, orden, productos, tenant, owner,
    ):
        """Si algún día alguien agrega un total guardado a OpenOrder, este
        test se cae — y tiene que caerse: un contador acumulado SÍ sufre
        lost update con 12 garzones escribiendo a la vez."""
        assert not hasattr(orden, "total") or callable(getattr(orden, "total", None)), (
            "OpenOrder no debe tener un total ESCRITO en la fila; "
            "calcularlo desde las líneas es lo que hace segura la concurrencia"
        )


class TestReintentoDuplicado:
    """Golpea el ENDPOINT real, no una réplica de su lógica."""

    def _cliente(self, usuario):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=usuario)
        return c

    def test_el_mismo_batch_en_paralelo_no_debe_duplicar(
        self, orden, productos, tenant, owner, store,
    ):
        """WiFi inestable: la response se pierde y el cliente reintenta.

        Sin lock, los dos intentos cuentan 0 y ambos insertan.
        """
        key = uuid.uuid4().hex
        cuerpo = {
            "idempotency_key": key,
            "lines": [{"product_id": productos[0].id, "qty": 1}],
        }
        url = f"/api/tables/orders/{orden.id}/add-lines/"
        codigos = []

        def enviar(i):
            r = self._cliente(owner).post(
                url, cuerpo, format="json", HTTP_X_STORE_ID=str(store.id),
            )
            codigos.append(r.status_code)

        errores = _correr_en_paralelo(enviar, 2)
        assert errores == [], f"hubo errores: {errores}"
        # 201 = el que creo, 200 = el que detecto la key y devolvio el estado.
        assert sorted(codigos) == [200, 201], (
            f"uno debe crear y el otro reconocer el duplicado; fue {codigos}"
        )

        n = OpenOrderLine.objects.filter(order=orden, add_lines_batch_key=key).count()
        assert n == 1, (
            f"el mismo batch se insertó {n} veces — el cliente ve su pedido "
            f"duplicado y se le cobra dos veces"
        )

    def test_batches_distintos_si_se_suman(
        self, orden, productos, tenant, owner, store,
    ):
        """El arreglo no puede volverse un candado que descarte comandas
        legítimas: dos garzones con batches distintos suman ambos."""
        url = f"/api/tables/orders/{orden.id}/add-lines/"

        def enviar(i):
            self._cliente(owner).post(
                url,
                {"idempotency_key": uuid.uuid4().hex,
                 "lines": [{"product_id": productos[i].id, "qty": 1}]},
                format="json", HTTP_X_STORE_ID=str(store.id),
            )

        errores = _correr_en_paralelo(enviar, 6)
        assert errores == [], f"hubo errores: {errores}"
        assert OpenOrderLine.objects.filter(order=orden).count() == 6
