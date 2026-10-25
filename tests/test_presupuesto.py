from datetime import date

VIEW = "views/5_Presupuesto.py"


def _week_rows(at):
    # Las filas del horizonte (arriba) van en negrita ("**fecha – fecha**");
    # las de "Balance semanal" (abajo) no, para poder distinguirlas acá.
    return [m for m in at.markdown if " – " in str(m.value) and "**" in str(m.value)]


def _balance_rows(at):
    return [m for m in at.markdown if " – " in str(m.value) and "**" not in str(m.value)]


def test_presupuesto_default_horizon_is_13_weeks(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert len(_week_rows(at)) == 13


def test_presupuesto_horizon_4_weeks(run_view, db):
    at = run_view(VIEW, role="admin")
    for r in at.radio:
        if r.key == "pp_horizon":
            r.set_value(4).run()
            break
    assert not at.exception
    assert len(_week_rows(at)) == 4


def test_presupuesto_horizon_26_weeks(run_view, db):
    at = run_view(VIEW, role="admin")
    for r in at.radio:
        if r.key == "pp_horizon":
            r.set_value(26).run()
            break
    assert not at.exception
    assert len(_week_rows(at)) == 26


def test_presupuesto_shows_pending_invoice_in_its_week(run_view, db):
    db.invoices.append({
        "id": "i1", "vendor": "P", "invoice_number": "F1", "branch": "Sucursal 1",
        "doc_type": "contado", "amount": 500.0,
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("1 pago(s)" in str(m.value) for m in at.markdown)


def test_balance_semanal_shows_debido_pagado_saldo(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 300.0,
        "issue_date": date.today().isoformat(), "due_date": date.today().isoformat(), "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Debido" in text and "Pagado" in text and "Saldo pendiente" in text
    assert "S/ 300.00" in text


def test_balance_semanal_weeks_back_selector(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2026-01-01", "due_date": "2026-01-05", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    for r in at.radio:
        if r.key == "pp_weeks_back":
            r.set_value(4).run()
            break
    assert not at.exception
    assert len(_balance_rows(at)) == 4


def test_balance_semanal_empty_state(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    caps = " ".join(str(c.value) for c in at.caption)
    assert "No hay movimientos registrados todavía" in caps
