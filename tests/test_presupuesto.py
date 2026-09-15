from datetime import date

VIEW = "views/5_Presupuesto.py"


def _week_rows(at):
    return [m for m in at.markdown if " – " in str(m.value)]


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
