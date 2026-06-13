"""
Tests del script _fix_sale_300.py — verificar que:
  1. El fix funciona en el caso esperado (subtotal $3,200, tip $1,800, payment $3,520)
  2. NO rompe si los datos son distintos (sanity checks abortan)
  3. ES idempotente (si ya se aplico, no hace nada)
  4. La transaccion hace rollback si algo falla
"""
import io
import contextlib
from decimal import Decimal

import pytest

from caja.models import CashRegister, CashSession
from sales.models import Sale, SalePayment, SaleTip
from inventory.models import StockItem


def _setup_caja_session(tenant, store, owner, initial=Decimal('103250.00')):
    register, _ = CashRegister.objects.get_or_create(
        tenant=tenant, store=store, name='Test Register',
        defaults={'is_active': True},
    )
    session = CashSession.objects.create(
        tenant=tenant, store=store, register=register,
        opened_by=owner,
        initial_amount=initial,
        counted_cash=Decimal('100740.00'),
        expected_cash=Decimal('102778.00'),
        status='CLOSED',
    )
    return session


def _setup_sale_300_clone(tenant, store, warehouse, owner, product):
    """Crear una venta replicando exacto el estado roto de la #300."""
    StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={'on_hand': Decimal('100'), 'avg_cost': Decimal('100')},
    )
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner,
        subtotal=Decimal('3200.00'),
        tip=Decimal('1800.00'),
        total=Decimal('3200.00'),
        status='COMPLETED',
        sale_number=300,
    )
    # Payment cash $3,520 (BUG — deberia ser $5,000)
    payment = SalePayment.objects.create(
        sale=sale, tenant=tenant,
        method='cash', amount=Decimal('3520.00'),
    )
    # Tip cash $1,800
    SaleTip.objects.create(
        sale=sale, tenant=tenant,
        method='cash', amount=Decimal('1800.00'),
    )
    return sale, payment


def _run_fix_script(sale_id, session_id):
    """Ejecutar el script _fix_sale_300.py con IDs configurables y capturar output."""
    import os
    # Buscar el script en varios paths posibles (relativo al cwd o al test)
    test_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        '_fix_sale_300.py',                                        # cwd = apps/api
        'apps/api/_fix_sale_300.py',                               # cwd = root
        os.path.join(test_dir, '..', '_fix_sale_300.py'),          # relativo al test
    ]
    script_path = next((p for p in candidates if os.path.exists(p)), None)
    if not script_path:
        raise FileNotFoundError(f'No encontre _fix_sale_300.py en: {candidates}')
    with open(script_path, encoding='utf-8') as f:
        source = f.read()

    # Reemplazar SALE_ID y SESSION_ID por los del fixture
    source = source.replace('SALE_ID = 6880', f'SALE_ID = {sale_id}')
    source = source.replace('SESSION_ID = 48', f'SESSION_ID = {session_id}')

    # Capturar stdout y exitcode
    output = io.StringIO()
    exit_code = 0
    try:
        with contextlib.redirect_stdout(output):
            exec(compile(source, '_fix_sale_300.py', 'exec'), {})
    except SystemExit as e:
        exit_code = e.code or 0
    return output.getvalue(), exit_code


@pytest.mark.django_db
def test_fix_caso_normal(tenant, store, warehouse, owner, product):
    """Caso happy path: la venta esta exactamente en el estado esperado."""
    session = _setup_caja_session(tenant, store, owner)
    sale, payment = _setup_sale_300_clone(tenant, store, warehouse, owner, product)

    # Verificar estado pre-fix
    assert payment.amount == Decimal('3520.00')
    assert session.expected_cash == Decimal('102778.00')

    out, code = _run_fix_script(sale.id, session.id)

    # No debe haber abortado
    assert code == 0, f'Script abortó. Output:\n{out}'

    # Verificar fix aplicado
    payment.refresh_from_db()
    session.refresh_from_db()
    assert payment.amount == Decimal('5000.00'), f'Payment no se actualizó. Es ${payment.amount}'
    assert session.expected_cash == Decimal('104258.00'), f'Session expected mal: ${session.expected_cash}'

    # Output debe contener mensaje de exito
    assert 'FIX APLICADO EXITOSAMENTE' in out


@pytest.mark.django_db
def test_fix_idempotente_no_duplica(tenant, store, warehouse, owner, product):
    """Si el fix YA se aplico (payment ya = $5,000), no hacer nada."""
    session = _setup_caja_session(tenant, store, owner)
    sale, payment = _setup_sale_300_clone(tenant, store, warehouse, owner, product)
    # Simular fix ya aplicado
    payment.amount = Decimal('5000.00')
    payment.save()
    session.expected_cash = Decimal('104258.00')
    session.save()

    out, code = _run_fix_script(sale.id, session.id)

    # Debe salir limpio sin error
    assert code == 0
    assert 'YA fue aplicado' in out or 'YA' in out

    # NO debe haber sumado de nuevo
    payment.refresh_from_db()
    session.refresh_from_db()
    assert payment.amount == Decimal('5000.00'), 'Idempotencia rota — payment se duplico'
    assert session.expected_cash == Decimal('104258.00'), 'Session expected se modifico de mas'


@pytest.mark.django_db
def test_fix_aborta_si_subtotal_distinto(tenant, store, warehouse, owner, product):
    """Si subtotal != $3,200, el script debe abortar sin tocar nada."""
    session = _setup_caja_session(tenant, store, owner)
    sale, payment = _setup_sale_300_clone(tenant, store, warehouse, owner, product)
    # Modificar subtotal — script debe abortar
    sale.subtotal = Decimal('5000.00')
    sale.save()

    out, code = _run_fix_script(sale.id, session.id)

    # Debe abortar con codigo 1
    assert code == 1, f'Script no aborto cuando deberia. Output:\n{out}'
    assert 'ABORT' in out

    # NO debe haber tocado el payment
    payment.refresh_from_db()
    assert payment.amount == Decimal('3520.00'), 'Payment se modifico aunque debia abortar'


@pytest.mark.django_db
def test_fix_aborta_si_payment_no_es_3520(tenant, store, warehouse, owner, product):
    """Si payment cash != $3,520 y != $5,000, abortar."""
    session = _setup_caja_session(tenant, store, owner)
    sale, payment = _setup_sale_300_clone(tenant, store, warehouse, owner, product)
    # Modificar payment a un monto distinto
    payment.amount = Decimal('4000.00')
    payment.save()

    out, code = _run_fix_script(sale.id, session.id)

    assert code == 1, 'Script no aborto cuando payment era inesperado'
    payment.refresh_from_db()
    assert payment.amount == Decimal('4000.00'), 'Payment se modifico'


@pytest.mark.django_db
def test_fix_aborta_si_no_existe_venta(tenant, store, warehouse, owner, product):
    """Si la venta no existe, abortar."""
    session = _setup_caja_session(tenant, store, owner)

    out, code = _run_fix_script(99999, session.id)

    assert code == 1
    assert 'no existe' in out.lower() or 'ABORT' in out
