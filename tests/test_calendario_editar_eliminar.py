"""Editar (monto/fecha) y Eliminar directo desde el diálogo del día en
Calendario, junto al botón Pagado ya existente."""
from datetime import date

from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _seed_invoice(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })


# ---------- editar ----------

def test_dia_muestra_boton_editar(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Editar" for b in at.button)


def test_editar_precarga_monto_y_fecha(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    assert not at.exception
    ni = next(n for n in at.number_input if n.key == "cal_edit_monto")
    di = next(d for d in at.date_input if d.key == "cal_edit_fecha")
    assert ni.value == 100.0
    assert di.value == date(2020, 1, 15)


def test_guardar_edicion_actualiza_factura(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(250.0)
            break
    for di in at.date_input:
        if di.key == "cal_edit_fecha":
            di.set_value(date(2020, 1, 20))
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.invoices[0]["amount"] == 250.0
    assert db.invoices[0]["due_date"] == "2020-01-20"


def test_editar_letra_actualiza_monto_y_vencimiento(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-15",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(480.0)
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.letras[0]["monto"] == 480.0


def test_editar_gasto_actualiza_monto(run_view, db):
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler",
                       "branch": "Sucursal 1", "amount": 1000.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(1200.0)
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.expenses[0]["amount"] == 1200.0


def test_cancelar_edicion_no_cambia_nada(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    click(at, "Cancelar")
    assert not at.exception
    assert db.invoices[0]["amount"] == 100.0
    assert at.session_state["_cal_day"] == "2020-01-15"


# ---------- eliminar ----------

def test_dia_muestra_boton_eliminar(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Eliminar" for b in at.button)


def test_eliminar_pide_confirmacion(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "no se puede deshacer" in warns
    assert db.invoices   # todavía no se borró


def test_confirmar_eliminar_borra_factura(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.invoices == []


def test_confirmar_eliminar_borra_letra(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-15",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.letras == []


def test_confirmar_eliminar_borra_gasto(run_view, db):
    db.create_expense({"kind": "variable", "name": "Reparación", "category": "Servicios",
                       "branch": "Sucursal 1", "amount": 75.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.expenses == []


def test_cancelar_eliminar_no_borra_y_vuelve_al_dia(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "No, cancelar")
    assert not at.exception
    assert db.invoices
    assert at.session_state["_cal_day"] == "2020-01-15"
