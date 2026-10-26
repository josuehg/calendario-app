"""Seleccionar varios pagos del mismo día con casillas y marcarlos todos
como pagados de una sola vez, en vez de uno por uno."""
from datetime import date

from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _seed_tres(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    # vencimiento al 07 para que, con el plazo típico de 8 días, caiga el
    # mismo 15 que la factura y el gasto (así los tres quedan el mismo día).
    db.create_letra({"numero": "L-1", "monto": 200.0, "fecha_vencimiento": "2020-01-07",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler",
                       "branch": "Sucursal 1", "amount": 300.0, "due_date": "2020-01-15", "status": "pendiente"})


def _check(at, prefix):
    for cb in at.checkbox:
        if cb.key and cb.key.startswith(prefix):
            cb.set_value(True)
            return
    raise AssertionError(f"no se encontró checkbox {prefix!r}")


def test_boton_masivo_no_aparece_con_un_solo_item(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert not any("como pagadas" in b.label for b in at.button)


def test_boton_masivo_deshabilitado_sin_seleccion(run_view, db):
    _seed_tres(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    btn = next(b for b in at.button if "seleccionadas como pagadas" in b.label)
    assert btn.disabled


def test_seleccionar_dos_habilita_boton_con_conteo(run_view, db):
    _seed_tres(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    _check(at, "cal_sel_invoice_")
    _check(at, "cal_sel_letra_")
    at.run()
    btn = next(b for b in at.button if "seleccionada(s) como pagadas" in b.label)
    assert not btn.disabled
    assert "2 seleccionada" in btn.label


def test_confirmar_pago_masivo_marca_todas_con_misma_fecha(run_view, db):
    _seed_tres(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    _check(at, "cal_sel_invoice_")
    _check(at, "cal_sel_letra_")
    _check(at, "cal_sel_expense_")
    at.run()
    click(at, "como pagadas")
    assert not at.exception
    for di in at.date_input:
        if di.key == "cal_bulk_pay_fecha":
            di.set_value(date(2020, 1, 16)).run()
            break
    click(at, "Confirmar pago de 3")
    assert not at.exception
    assert db.invoices[0]["status"] == "pagada" and db.invoices[0]["paid_at"] == "2020-01-16"
    assert db.letras[0]["estado"] == "pagada" and db.letras[0]["fecha_pago"] == "2020-01-16"
    assert db.expenses[0]["status"] == "pagado" and db.expenses[0]["paid_at"] == "2020-01-16"


def test_pago_masivo_solo_afecta_las_seleccionadas(run_view, db):
    _seed_tres(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    _check(at, "cal_sel_invoice_")   # solo la factura
    at.run()
    click(at, "como pagadas")
    click(at, "Confirmar pago de 1")
    assert not at.exception
    assert db.invoices[0]["status"] == "pagada"
    assert db.letras[0]["estado"] == "pendiente"
    assert db.expenses[0]["status"] == "pendiente"


def test_cancelar_pago_masivo_no_cambia_nada(run_view, db):
    _seed_tres(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    _check(at, "cal_sel_invoice_")
    _check(at, "cal_sel_letra_")
    at.run()
    click(at, "como pagadas")
    click(at, "Cancelar")
    assert not at.exception
    assert db.invoices[0]["status"] == "pendiente"
    assert db.letras[0]["estado"] == "pendiente"
    assert at.session_state["_cal_day"] == "2020-01-15"
