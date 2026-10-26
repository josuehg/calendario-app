"""Registrar pagos directo desde el diálogo de 'Pagos del día' en Calendario."""
from datetime import date

from tests.conftest import click

VIEW = "views/4_Calendario.py"


def test_dia_muestra_boton_pagado_por_item(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert not at.exception
    assert any(b.label == "Pagado" for b in at.button)


def test_click_pagado_abre_dialogo_de_confirmacion(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    assert not at.exception
    assert any("Confirmar pago" in b.label for b in at.button)
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Prov A" in text


def test_confirmar_pago_marca_factura_pagada(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    for di in at.date_input:
        if di.key == "cal_pay_fecha":
            di.set_value(date(2020, 1, 15)).run()
            break
    click(at, "Confirmar pago")
    assert not at.exception
    assert db.invoices[0]["status"] == "pagada"
    assert db.invoices[0]["paid_by"] == "Administrador"
    assert db.invoices[0]["paid_at"] == "2020-01-15"


def test_confirmar_pago_de_letra(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-15",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    click(at, "Confirmar pago")
    assert not at.exception
    assert db.letras[0]["estado"] == "pagada"


def test_confirmar_pago_de_gasto(run_view, db):
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler",
                       "branch": "Sucursal 1", "amount": 1000.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    click(at, "Confirmar pago")
    assert not at.exception
    assert db.expenses[0]["status"] == "pagado"
    assert db.expenses[0]["paid_by"] == "Administrador"


def test_cancelar_no_marca_pagado_y_vuelve_al_dia(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    click(at, "Cancelar")
    assert not at.exception
    assert db.invoices[0]["status"] == "pendiente"
    assert at.session_state["_cal_day"] == "2020-01-15"   # el diálogo del día sigue "abierto"


def test_pago_confirmado_desaparece_de_la_lista_del_dia(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Pagado")
    click(at, "Confirmar pago")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Prov A" not in text
