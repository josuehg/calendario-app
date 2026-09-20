"""Panel 'Vencimientos sospechosos' en Configuración: detecta y corrige
facturas a crédito cuyo vencimiento no cuadra con emisión + plazo del
proveedor (ver bug real de Representaciones Castillo)."""
from tests.conftest import click

VIEW = "views/6_Configuracion.py"


def test_shows_success_when_nothing_suspicious(run_view, db):
    db.create_vendor({"name": "Prov OK", "ruc": None, "doc_type": "credito", "term_days": 30})
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov OK", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-10-01", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("No hay ninguna" in s.value for s in at.success)


def test_flags_mismatched_due_date_with_expected_value(run_view, db):
    db.create_vendor({"name": "Representaciones Castillo", "ruc": None, "doc_type": "credito", "term_days": 90})
    db.create_invoice({
        "branch": "Colón", "vendor": "Representaciones Castillo", "invoice_number": "F100-676693",
        "document_type": "Factura", "doc_type": "credito", "term_days": 90, "amount": 690.81,
        "issue_date": "2026-09-15", "due_date": "2026-09-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    md = " ".join(str(m.value) for m in at.markdown) + " ".join(str(c.value) for c in at.caption)
    assert "F100-676693" in md
    assert "2026-12-14" in md or "14/12/26" in md
    assert not any("No hay ninguna" in s.value for s in at.success)


def test_ignores_manually_agreed_different_term(run_view, db):
    """No es un error garantizado: si el usuario pactó un plazo distinto para
    esa factura puntual, no debe forzarse — pero sí debe listarse para revisión."""
    db.create_vendor({"name": "Prov X", "ruc": None, "doc_type": "credito", "term_days": 75})
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov X", "invoice_number": "F-14d",
        "document_type": "Factura", "doc_type": "credito", "term_days": 75, "amount": 50.0,
        "issue_date": "2026-09-10", "due_date": "2026-09-24", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    md = " ".join(str(m.value) for m in at.markdown)
    assert "F-14d" in md


def test_ignores_pagada_and_contado(run_view, db):
    db.create_vendor({"name": "Prov Y", "ruc": None, "doc_type": "credito", "term_days": 30})
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Y", "invoice_number": "F-pagada",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 50.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pagada",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Contado", "invoice_number": "F-contado",
        "document_type": "Factura", "doc_type": "contado", "amount": 50.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert any("No hay ninguna" in s.value for s in at.success)


def test_corregir_button_fixes_due_date(run_view, db):
    db.create_vendor({"name": "Representaciones Castillo", "ruc": None, "doc_type": "credito", "term_days": 90})
    db.create_invoice({
        "branch": "Colón", "vendor": "Representaciones Castillo", "invoice_number": "F100-676693",
        "document_type": "Factura", "doc_type": "credito", "term_days": 90, "amount": 690.81,
        "issue_date": "2026-09-15", "due_date": "2026-09-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    click(at, "Corregir")
    assert not at.exception
    assert db.invoices[0]["due_date"] == "2026-12-14"
    assert any("No hay ninguna" in s.value for s in at.success)   # ya no queda ninguna sospechosa
