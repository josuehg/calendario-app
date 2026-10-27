"""Cambiar de mes debe cerrar cualquier diálogo de día abierto.

Antes de este fix, si el usuario cerraba el diálogo con la X nativa de
Streamlit (que no corre código, solo lo oculta en el cliente) y luego
navegaba de mes, `_cal_day` seguía seteado y el diálogo se reabría solo
en el siguiente rerun, mostrando el día del mes anterior."""
from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _seed(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })


def test_ir_a_mes_anterior_cierra_el_dialogo_del_dia(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Pagado" for b in at.button)  # diálogo abierto

    at = click(at, "← Anterior")
    assert not at.exception
    assert at.session_state["_cal_day"] is None
    assert not any(b.label == "Pagado" for b in at.button)  # diálogo ya no se reabre


def test_ir_a_mes_siguiente_cierra_el_dialogo_del_dia(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Pagado" for b in at.button)

    at = click(at, "Siguiente →")
    assert not at.exception
    assert at.session_state["_cal_day"] is None
    assert not any(b.label == "Pagado" for b in at.button)
