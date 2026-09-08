# -*- coding: utf-8 -*-
"""
tests/test_feriados_por_negocio.py — lo que un negocio aprende de un feriado
no puede tocar a los demas.

Auditoria del 08/09/26, hallazgo 2. El calendario de feriados es compartido
(al 08/09 eran 126 filas, TODAS globales) y el aprendizaje escribia el
multiplicador medido en `Holiday.learned_multiplier`, o sea encima de esa fila
compartida. Y desde dos lugares:

  - `track_forecast_accuracy` filtraba "de este negocio o globales" y le
    escribia a todos los que encontraba, incluidos los nacionales;
  - `train_forecast_models` no filtraba por negocio en absoluto, asi que
    tambien habria pisado los feriados propios de otro cliente.

Al leer, `apply_holiday_adjustments` mezcla 60% de lo aprendido con 40% de lo
configurado: el valor aprendido MANDA. O sea que las ventas de una cafeteria
en Valdivia habrian fijado el multiplicador de Fiestas Patrias de cualquier
otro cliente, por encima de su propia configuracion. En produccion habia 20
feriados globales ya escritos con datos de Marbrava.

Ahora lo aprendido vive en `HolidayLearning`, una fila por (negocio, feriado),
y el calendario vuelve a ser una referencia que nadie escribe.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from core.models import Tenant, Warehouse
from stores.models import Store
from forecast import services
from forecast.models import DailySales, Holiday, HolidayLearning

D = Decimal
HOY = datetime.date.today()
AYER = HOY - datetime.timedelta(days=1)


@pytest.fixture
def otro_negocio(db):
    t = Tenant(name="Otra Empresa", slug="otra-empresa")
    t._skip_subscription = True
    t.save()
    s = Store.objects.create(tenant=t, name="Local")
    Warehouse.objects.create(tenant=t, store=s, name="Bodega")
    return t


def _feriado_nacional(fecha=None, nombre="Fiestas Patrias"):
    return Holiday.objects.create(
        tenant=None, name=nombre, date=fecha or AYER,
        demand_multiplier=D("1.50"), pre_days=1, pre_multiplier=D("1.20"),
    )


def _pronosticos(desde, n=3):
    return [{"date": desde + datetime.timedelta(days=i), "qty_predicted": D("10"),
             "lower_bound": D("7"), "upper_bound": D("13")} for i in range(n)]


@pytest.mark.django_db
class TestLoAprendidoEsDeCadaNegocio:
    def test_el_seguimiento_no_escribe_el_calendario_compartido(
        self, tenant, store, warehouse, product, otro_negocio,
    ):
        feriado = _feriado_nacional()
        for i in range(1, 15):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=AYER - datetime.timedelta(days=i), qty_sold=D("10"))
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, date=AYER, qty_sold=D("30"))

        call_command("track_forecast_accuracy", "--date", AYER.isoformat(),
                     "--tenant", str(tenant.id), verbosity=0)

        feriado.refresh_from_db()
        assert feriado.learned_multiplier is None, (
            "se escribio el feriado nacional: lo aprendido por un negocio le "
            "llegaria a todos los demas")
        assert not HolidayLearning.objects.filter(tenant=otro_negocio).exists()

    def test_el_entrenamiento_tampoco(self, tenant, store, warehouse, product, otro_negocio):
        feriado = _feriado_nacional(fecha=HOY - datetime.timedelta(days=20))
        for i in range(1, 60):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=HOY - datetime.timedelta(days=i), qty_sold=D("10"))
        DailySales.objects.filter(tenant=tenant, date=feriado.date).update(qty_sold=D("40"))

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        feriado.refresh_from_db()
        assert feriado.learned_multiplier is None
        assert not HolidayLearning.objects.filter(tenant=otro_negocio).exists()

    def test_cada_negocio_ve_lo_suyo_y_no_lo_del_otro(
        self, tenant, store, warehouse, product, otro_negocio,
    ):
        """El corazon del hallazgo: dos negocios, el mismo feriado nacional,
        multiplicadores distintos y ninguno contamina al otro."""
        feriado = _feriado_nacional(fecha=HOY + datetime.timedelta(days=2))
        HolidayLearning.objects.create(tenant=tenant, holiday=feriado, learned_multiplier=D("2.50"))
        HolidayLearning.objects.create(tenant=otro_negocio, holiday=feriado, learned_multiplier=D("0.60"))

        mio = services._load_holidays_for_horizon(tenant, _pronosticos(HOY + datetime.timedelta(days=1)))
        suyo = services._load_holidays_for_horizon(otro_negocio, _pronosticos(HOY + datetime.timedelta(days=1)))

        assert [h.learned_multiplier for h in mio] == [D("2.50")]
        assert [h.learned_multiplier for h in suyo] == [D("0.60")]
        feriado.refresh_from_db()
        assert feriado.learned_multiplier is None, "el calendario sigue sin escribirse"

    def test_un_negocio_sin_aprendizaje_usa_solo_lo_configurado(
        self, tenant, store, warehouse, product, otro_negocio,
    ):
        feriado = _feriado_nacional(fecha=HOY + datetime.timedelta(days=2))
        HolidayLearning.objects.create(tenant=tenant, holiday=feriado, learned_multiplier=D("2.50"))
        suyo = services._load_holidays_for_horizon(otro_negocio, _pronosticos(HOY + datetime.timedelta(days=1)))
        assert [h.learned_multiplier for h in suyo] == [None]

    def test_el_multiplicador_aprendido_llega_al_pronostico(self, tenant, store, warehouse, product):
        """Que no sea un dato muerto: con 2,5 aprendido y 1,5 configurado, la
        mezcla 60/40 da 2,1 y el pronostico del dia sube."""
        from forecast.engine import apply_holiday_adjustments
        feriado = _feriado_nacional(fecha=HOY + datetime.timedelta(days=1))
        HolidayLearning.objects.create(tenant=tenant, holiday=feriado, learned_multiplier=D("2.50"))
        fcs = _pronosticos(HOY + datetime.timedelta(days=1), n=1)
        apply_holiday_adjustments(fcs, services._load_holidays_for_horizon(tenant, fcs))
        assert fcs[0]["qty_predicted"] == D("21.000"), fcs[0]["qty_predicted"]


@pytest.mark.django_db
class TestPrecedencia:
    def test_el_feriado_propio_le_gana_al_nacional_en_la_misma_fecha(
        self, tenant, store, warehouse, product,
    ):
        """Antes ganaba el que devolviera la base, al azar: el ajuste arma un
        diccionario por fecha donde el ultimo pisa al anterior."""
        fecha = HOY + datetime.timedelta(days=2)
        _feriado_nacional(fecha=fecha, nombre="Nacional")
        propio = Holiday.objects.create(
            tenant=tenant, name="Aniversario del local", date=fecha,
            demand_multiplier=D("0.20"), pre_days=0, pre_multiplier=D("1.00"),
            scope=Holiday.SCOPE_CUSTOM,
        )
        elegidos = services._load_holidays_for_horizon(tenant, _pronosticos(HOY + datetime.timedelta(days=1)))
        assert [h.id for h in elegidos] == [propio.id]
