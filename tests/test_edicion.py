"""Editar / eliminar facturas y letras."""
from datetime import date

import pytest

from tests.conftest import click, widget


# ---------- facturas ----------

def test_update_invoice_changes_fields(db):
    inv = db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Mal Escrito", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    db.update_invoice(inv["id"], {"vendor": "Bien Escrito SAC", "amount": 250.5})
    got = db.list_invoices()[0]
    assert got["vendor"] == "Bien Escrito SAC"
    assert got["amount"] == 250.5


def test_consolidado_edit_dialog_saves(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Original", "invoice_number": "F-9",
        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    at = run_view("views/2_Consolidado.py", role="admin")
    click(at, "Editar")
    for ti in at.text_input:
        if ti.key == "ei_vendor":
            ti.set_value("Corregido SAC").run()
    for b in at.button:
        if b.label == "Guardar":
            b.click().run()
            break
    assert not at.exception
    assert db.list_invoices()[0]["vendor"] == "Corregido SAC"


def test_delete_dialog_warns_for_canjeada(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "X", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-10-01", "status": "canjeada",
    })
    at = run_view("views/2_Consolidado.py", role="admin")
    click(at, "Eliminar")
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "canjeada" in warns and "letra" in warns


def test_db_delete_invoice(db):
    inv = db.create_invoice({
        "branch": "Sucursal 1", "vendor": "X", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pagada",
    })
    db.delete_invoice(inv["id"])
    assert db.invoices == []


# ---------- letras ----------

@pytest.fixture
def with_letras(db):
    db.create_letra({"numero": "P-1", "monto": 1000.0, "fecha_vencimiento": "2026-10-10",
                     "vendor": "Lab Suelto", "branch": "Sucursal 2"})
    db.invoices.append({"id": "i1", "vendor": "Prov Canje", "invoice_number": "FC-1",
                        "branch": "Sucursal 1", "doc_type": "credito", "amount": 500.0,
                        "due_date": "2026-09-01", "issue_date": "2026-08-01", "status": "canjeada"})
    db.create_canje(["i1"], [{"numero": "C-1", "monto": 500.0, "fecha_vencimiento": "2026-11-01"}],
                    created_by="Administrador")
    return db


def test_update_standalone_letra(with_letras):
    l = next(x for x in with_letras.letras if x["numero"] == "P-1")
    with_letras.update_letra(l["id"], {"monto": 1234.0, "fecha_vencimiento": "2026-10-20"})
    got = next(x for x in with_letras.list_letras() if x["id"] == l["id"])
    assert got["monto"] == 1234.0 and got["fecha_vencimiento"] == "2026-10-20"


def test_update_canje_letra_monto(with_letras):
    l = next(x for x in with_letras.letras if x["numero"] == "C-1")
    with_letras.update_letra(l["id"], {"monto": 480.0})
    assert next(x for x in with_letras.letras if x["id"] == l["id"])["monto"] == 480.0


def test_delete_canje_letra(with_letras):
    l = next(x for x in with_letras.letras if x["numero"] == "C-1")
    with_letras.delete_letra(l["id"])
    assert all(x["numero"] != "C-1" for x in with_letras.letras)
    # la factura sigue canjeada (borrar la letra no la revierte)
    assert with_letras.invoices[0]["status"] == "canjeada"


def test_todas_las_letras_tab_renders(run_view, with_letras):
    at = run_view("views/3_Canjear_a_Letras.py", role="admin")
    assert not at.exception
    labels = " ".join(str(m.value) for m in at.markdown)
    assert "letra(s)" in labels


def test_letra_manage_dialog_edit(run_view, with_letras):
    at = run_view("views/3_Canjear_a_Letras.py", role="admin")
    for b in at.button:
        if b.key and b.key.startswith("lt_mng_"):
            b.click().run()
            break
    for ni in at.number_input:
        if ni.key == "lt_monto":
            ni.set_value(777.0).run()
    for b in at.button:
        if b.label == "Guardar cambios":
            b.click().run()
            break
    assert not at.exception
    assert any(l["monto"] == 777.0 for l in with_letras.letras)
