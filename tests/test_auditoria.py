from datetime import date

import pytest

from tests.conftest import click, widget


def test_current_actor(db, monkeypatch):
    import utils
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {"auth_role": "branch", "auth_branch": "ZOLEZZI A"}, raising=False)
    assert utils.current_actor() == "ZOLEZZI A"
    monkeypatch.setattr(st, "session_state", {"auth_role": "admin"}, raising=False)
    assert utils.current_actor() == "Administrador"


def test_invoice_records_registering_branch(run_view, db):
    db.vendors.append({"id": 1, "name": "Bodega Sur", "ruc": "20999999999",
                       "doc_type": "contado", "term_days": None})
    at = run_view("views/1_Nueva_Factura.py", role="branch", branch="ZOLEZZI A")
    widget(at, "nf_query").set_value("Bodega Sur").run()
    widget(at, "nf_invoice_number").set_value("B-1").run()
    widget(at, "nf_amount", "number_input").set_value(100.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    click(at, "Confirmar y guardar")
    assert db.invoices[0]["registered_by"] == "ZOLEZZI A"


def test_admin_registration_labeled_administrador(run_view, db):
    db.vendors.append({"id": 1, "name": "Bodega Sur", "ruc": "20999999999",
                       "doc_type": "contado", "term_days": None})
    at = run_view("views/1_Nueva_Factura.py", role="admin")
    widget(at, "nf_query").set_value("Bodega Sur").run()
    widget(at, "nf_invoice_number").set_value("B-2").run()
    widget(at, "nf_amount", "number_input").set_value(100.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    click(at, "Confirmar y guardar")
    assert db.invoices[0]["registered_by"] == "Administrador"


def test_generated_fixed_expense_marked_automatic(db):
    db.create_fixed_expense({"name": "Alquiler", "category": "Alquiler", "branch": None,
                             "amount": 3000.0, "pay_day": 5})
    db.ensure_expense_instances()
    assert all(e["registered_by"] == "Gasto fijo (automático)" for e in db.expenses)


def test_variable_expense_and_payment_record_actor(run_view, db):
    at = run_view("views/7_Gastos.py", role="admin")
    for ti in at.text_input:
        if ti.label == "Descripción":
            ti.set_value("Reparación").run()
    for ni in at.number_input:
        if ni.label.startswith("Monto"):
            ni.set_value(200.0).run()
    for b in at.button:
        if "Registrar gasto variable" in b.label:
            b.click().run()
    assert db.expenses[0]["registered_by"] == "Administrador"

    eid = db.expenses[0]["id"]
    db.set_expense_status(eid, "pagado", "2026-09-10", paid_by="Administrador")
    assert db.expenses[0]["paid_by"] == "Administrador"


def test_canje_records_creator(db):
    db.invoices.append({"id": "i1", "vendor": "P", "invoice_number": "F1", "branch": "S1",
                        "doc_type": "credito", "amount": 500.0, "due_date": "2026-10-01",
                        "issue_date": "2026-09-01", "status": "pendiente"})
    db.create_canje(["i1"], [{"numero": "L1", "monto": 500.0, "fecha_vencimiento": "2026-11-01"}],
                    created_by="Administrador")
    assert db.canjes[0]["created_by"] == "Administrador"
    assert db.list_letras()[0]["estado"] == "pendiente"


def test_consolidado_shows_registered_by_column(run_view, db):
    db.invoices.append({"id": "i1", "vendor": "Prov", "invoice_number": "F1", "branch": "Sucursal 1",
                        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
                        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
                        "registered_by": "Sucursal 1"})
    at = run_view("views/2_Consolidado.py", role="admin")
    assert not at.exception
    df = at.dataframe[0].value
    assert "Registrado por" in list(df.columns)
    assert "Sucursal 1" in df["Registrado por"].tolist()
