from datetime import date

import pytest

from tests.conftest import click


@pytest.fixture
def utils(db):
    import utils as u
    return u


def test_standalone_letra_event_uses_its_own_data(utils):
    letras = [{
        "id": "L1", "canje_id": None, "estado": "pendiente", "numero": "001-A",
        "monto": 5000.0, "fecha_vencimiento": "2026-10-15",
        "vendor": "Laboratorio X", "branch": "Sucursal 2",
    }]
    ev = utils.get_payment_events([], letras, [], True)
    assert len(ev) == 1
    e = ev[0]
    assert e["kind"] == "letra"
    assert e["vendor"] == "Laboratorio X"
    assert e["branch"] == "Sucursal 2"
    assert "programada" in e["label"]
    assert e["amount"] == 5000.0


def test_canje_letra_still_derives_from_invoices(utils):
    invoices = [{"id": "i1", "vendor": "Prov Z", "invoice_number": "F9", "branch": "Sucursal 1",
                 "doc_type": "credito", "amount": 300.0, "due_date": "2026-09-01", "status": "canjeada"}]
    canje_facturas = [{"canje_id": "c1", "invoice_id": "i1"}]
    letras = [{"id": "L2", "canje_id": "c1", "estado": "pendiente", "numero": "L-1",
               "monto": 300.0, "fecha_vencimiento": "2026-11-01"}]
    ev = utils.get_payment_events(invoices, letras, canje_facturas, True)
    letra_ev = [e for e in ev if e["kind"] == "letra"][0]
    assert letra_ev["vendor"] == "Prov Z"
    assert "1 factura" in letra_ev["label"]


def test_create_standalone_letra_via_view(run_view, db):
    at = run_view("views/3_Canjear_a_Letras.py", role="admin")
    for ti in at.text_input:
        if ti.label == "Proveedor":
            ti.set_value("Droguería Central").run()
        if ti.label == "N° de letra":
            ti.set_value("2026-045").run()
    for ni in at.number_input:
        if ni.label.startswith("Monto"):
            ni.set_value(8200.0).run()
    for di in at.date_input:
        if di.label == "Vencimiento":
            di.set_value(date(2026, 11, 20)).run()
    click(at, "Registrar letra")
    assert not at.exception
    assert len(db.letras) == 1
    l = db.letras[0]
    assert l["canje_id"] is None
    assert l["vendor"] == "Droguería Central"
    assert l["monto"] == 8200.0
    assert l["estado"] == "pendiente"


def test_standalone_letra_shows_in_calendar_and_budget(run_view, db):
    db.create_letra({"numero": "X", "monto": 1000.0, "fecha_vencimiento": "2026-10-01",
                     "vendor": "Prov", "branch": "Sucursal 1"})
    at_cal = run_view("views/4_Calendario.py", role="admin")
    assert not at_cal.exception
    at_pre = run_view("views/5_Presupuesto.py", role="admin")
    assert not at_pre.exception


def test_delete_standalone_letra(db):
    l = db.create_letra({"numero": "Y", "monto": 500.0, "fecha_vencimiento": "2026-10-01",
                         "vendor": "P", "branch": "Sucursal 1"})
    db.delete_letra(l["id"])
    assert db.letras == []


def test_canje_shows_summary_before_saving(run_view, db):
    db.invoices.append({"id": "i1", "vendor": "Prov A", "invoice_number": "F-1", "branch": "Sucursal 1",
                        "doc_type": "credito", "amount": 400.0, "due_date": "2026-10-01",
                        "issue_date": "2026-09-01", "status": "pendiente"})
    at = run_view("views/3_Canjear_a_Letras.py", role="admin")
    # seleccionar la factura
    at.multiselect[0].select(
        "Prov A · Fact. F-1 · Sucursal 1 · S/ 400.00 · vence 01/10/26"
    ).run()
    # fecha de la letra 1
    for di in at.date_input:
        if di.key and di.key.startswith("fecha_"):
            di.set_value(date(2026, 11, 1)).run()
    click(at, "Revisar y confirmar canje")
    assert not at.exception
    assert at.session_state["_canje_pending"] is not None      # abrió resumen, no guardó
    assert db.canjes == []
    click(at, "Confirmar y guardar")
    assert not at.exception
    assert len(db.canjes) == 1
    assert db.invoices[0]["status"] == "canjeada"
    assert len(db.list_letras()) == 1
