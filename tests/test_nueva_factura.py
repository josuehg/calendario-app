from datetime import date

import pytest

from tests.conftest import click, widget

VIEW = "views/1_Nueva_Factura.py"


@pytest.fixture
def seeded(db):
    db.vendors.append({
        "id": 1, "name": "Droguería Norte", "ruc": "20123456789",
        "doc_type": "credito", "term_days": 30,
    })
    db.vendors.append({
        "id": 2, "name": "Bodega Sur", "ruc": "20999999999",
        "doc_type": "contado", "term_days": None,
    })
    return db


def _search(at, text):
    return widget(at, "nf_query").set_value(text).run()


def test_renders_with_new_names(run_view, seeded):
    at = run_view(VIEW, role="branch")
    assert not at.exception
    assert any("Registro de documentos de compra" in t.value for t in at.title)
    assert any(b.label == "Registrar documento" for b in at.button)


def test_limpiar_clears_existing_vendor(run_view, seeded):
    at = run_view(VIEW, role="branch")
    _search(at, "Droguería Norte")
    assert widget(at, "nf_query").value == "Droguería Norte"
    assert [i.value for i in at.info]                      # muestra "trabaja a crédito…"
    click(at, "Limpiar campos")
    assert widget(at, "nf_query").value == ""
    assert not [i.value for i in at.info]
    assert not [s.value for s in at.success]


def test_limpiar_clears_new_vendor_fields(run_view, seeded):
    at = run_view(VIEW, role="branch")
    _search(at, "Proveedor Que No Existe")
    widget(at, "nf_new_vendor_name").set_value("Proveedor Que No Existe").run()
    widget(at, "nf_new_vendor_ruc").set_value("20111111111").run()
    widget(at, "nf_invoice_number").set_value("F1-1").run()
    click(at, "Limpiar campos")
    assert widget(at, "nf_query").value == ""
    assert widget(at, "nf_new_vendor_name") is None       # el bloque de proveedor nuevo se fue
    assert widget(at, "nf_invoice_number").value == ""


def test_credito_shows_due_date_and_recalcular(run_view, seeded):
    at = run_view(VIEW, role="branch")
    _search(at, "Droguería Norte")
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 8, 27)).run()
    widget(at, "nf_due_date", "date_input").set_value(date(2026, 1, 1)).run()
    click(at, "Recalcular")
    assert not at.exception
    assert widget(at, "nf_due_date", "date_input").value == date(2026, 9, 26)


def test_new_vendor_ruc_must_be_11_digits(run_view, seeded):
    at = run_view(VIEW, role="branch")
    _search(at, "Nuevo Prov SAC")
    widget(at, "nf_new_vendor_name").set_value("Nuevo Prov SAC").run()
    widget(at, "nf_new_vendor_ruc").set_value("123").run()
    widget(at, "nf_invoice_number").set_value("F1-1").run()
    widget(at, "nf_amount", "number_input").set_value(100.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    assert any("11 díg" in e.value for e in at.error)


def test_full_flow_then_review_then_clear(run_view, seeded):
    at = run_view(VIEW, role="branch")
    _search(at, "Bodega Sur")
    widget(at, "nf_invoice_number").set_value("B001-1").run()
    widget(at, "nf_amount", "number_input").set_value(250.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    assert at.session_state["nf_pending"] is not None      # abrió el diálogo
    click(at, "Confirmar y guardar")
    assert not at.exception
    assert len(seeded.invoices) == 1
    assert seeded.invoices[0]["invoice_number"] == "B001-1"
    assert any("Registrado:" in s.value for s in at.success)
    assert widget(at, "nf_invoice_number").value == "B001-1"   # sigue a la vista
    click(at, "Registrar otro documento")
    assert widget(at, "nf_invoice_number").value == ""
    assert widget(at, "nf_query").value == ""


def test_duplicate_blocked_same_vendor_and_number(run_view, seeded):
    seeded.invoices.append({
        "id": "x", "vendor": "Bodega Sur", "invoice_number": "B001-1",
        "branch": "Sucursal 2", "issue_date": "2026-08-01", "amount": 100.0, "status": "pendiente",
    })
    at = run_view(VIEW, role="branch")
    _search(at, "Bodega Sur")
    widget(at, "nf_invoice_number").set_value("B001-1").run()
    widget(at, "nf_amount", "number_input").set_value(250.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    assert any("Ya está registrado" in e.value for e in at.error)
    assert "nf_pending" not in at.session_state or not at.session_state["nf_pending"]


def test_same_number_other_vendor_is_allowed(run_view, seeded):
    seeded.invoices.append({
        "id": "x", "vendor": "Bodega Sur", "invoice_number": "F-777",
        "branch": "Sucursal 2", "issue_date": "2026-08-01", "amount": 100.0, "status": "pendiente",
    })
    at = run_view(VIEW, role="branch")
    _search(at, "Droguería Norte")
    widget(at, "nf_invoice_number").set_value("F-777").run()
    widget(at, "nf_amount", "number_input").set_value(250.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    widget(at, "nf_due_date", "date_input").set_value(date(2026, 10, 1)).run()
    click(at, "Registrar documento")
    assert at.session_state["nf_pending"] is not None
