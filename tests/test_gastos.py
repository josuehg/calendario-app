from datetime import date

import pytest

from tests.conftest import click, widget

VIEW = "views/7_Gastos.py"


def test_gastos_view_renders(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Gastos" in t.value for t in at.title)


def test_variable_expense_created(run_view, db):
    at = run_view(VIEW, role="admin")
    widget(at, "", "text_input")  # noop; localizamos por label abajo
    for ti in at.text_input:
        if ti.label == "Descripción":
            ti.set_value("Reparación de vitrina").run()
    for ni in at.number_input:
        if ni.label.startswith("Monto"):
            ni.set_value(450.0).run()
    for b in at.button:
        if "Registrar gasto variable" in b.label:
            b.click().run()
    assert not at.exception
    assert len(db.expenses) == 1
    assert db.expenses[0]["kind"] == "variable"
    assert db.expenses[0]["amount"] == 450.0


def test_fixed_expense_generates_instances(db):
    db.create_fixed_expense({
        "name": "Alquiler", "category": "Alquiler", "branch": None,
        "amount": 3000.0, "pay_day": 5,
    })
    db.ensure_expense_instances()
    gen = [e for e in db.expenses if e["fixed_expense_id"]]
    assert len(gen) == 4                       # mes actual + 3
    db.ensure_expense_instances()              # idempotente
    assert len([e for e in db.expenses if e["fixed_expense_id"]]) == 4


def test_inactive_fixed_expense_not_generated(db):
    fx = db.create_fixed_expense({
        "name": "Publicidad", "category": "Servicios", "branch": None,
        "amount": 500.0, "pay_day": 10,
    })
    db.update_fixed_expense(fx["id"], {"active": False})
    db.ensure_expense_instances()
    assert db.expenses == []


def test_expenses_feed_calendar_and_budget_not_resumen(run_view, db):
    db.create_fixed_expense({
        "name": "Alquiler", "category": "Alquiler", "branch": None,
        "amount": 3000.0, "pay_day": 5,
    })
    at_cal = run_view("views/4_Calendario.py", role="admin")
    assert not at_cal.exception
    at_pre = run_view("views/5_Presupuesto.py", role="admin")
    assert not at_pre.exception
    # Resumen no debe incluir gastos: sin facturas, todo en 0
    at_res = run_view("views/0_Resumen.py", role="admin")
    assert not at_res.exception
    metrics = {m.label: m.value for m in at_res.metric}
    assert metrics.get("Total pendiente") == "S/ 0.00"


def test_fijos_tab_shows_grouped_stats(run_view, db):
    db.create_fixed_expense({"name": "Alquiler A", "category": "Alquiler", "branch": "Sucursal 1",
                             "amount": 1000.0, "pay_day": 5})
    db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                             "amount": 3000.0, "pay_day": 28})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Total mensual comprometido") == "S/ 4,000.00"
    assert metrics.get("Activos / pausados") == "2 / 0"
    labels = [e.label for e in at.expander]
    assert any("Alquiler" in l for l in labels)
    assert any("Planilla" in l for l in labels)


def test_fijos_tab_group_by_branch(run_view, db):
    db.create_fixed_expense({"name": "Alquiler A", "category": "Alquiler", "branch": "Sucursal 1",
                             "amount": 1000.0, "pay_day": 5})
    db.create_fixed_expense({"name": "Servicios generales", "category": "Servicios", "branch": None,
                             "amount": 200.0, "pay_day": 10})
    at = run_view(VIEW, role="admin")
    for r in at.radio:
        if r.key == "fx_group_by":
            r.set_value("Sucursal").run()
            break
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any("Sucursal 1" in l for l in labels)
    assert any("General" in l for l in labels)


def test_urgency_pill_vencido_y_hoy(run_view, db):
    from datetime import timedelta
    today = date.today()
    db.create_expense({"kind": "variable", "name": "Vencido ya", "category": "Servicios",
                       "branch": None, "amount": 50.0,
                       "due_date": (today - timedelta(days=3)).isoformat(), "status": "pendiente"})
    db.create_expense({"kind": "variable", "name": "Hoy mismo", "category": "Servicios",
                       "branch": None, "amount": 60.0,
                       "due_date": today.isoformat(), "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    html = " ".join(str(m.value) for m in at.markdown)
    assert "Vencido hace 3 días" in html
    assert "Vence hoy" in html


def test_proximos_gastos_stats_and_grouping(run_view, db):
    db.create_expense({"kind": "variable", "name": "Gasto A", "category": "Alquiler",
                       "branch": "Sucursal 1", "amount": 500.0, "due_date": "2020-01-01",
                       "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Vencidos") == "1"
    labels = [e.label for e in at.expander]
    assert any("Alquiler" in l for l in labels)


def test_proximos_gastos_sin_agrupar(run_view, db):
    db.create_expense({"kind": "variable", "name": "Gasto A", "category": "Alquiler",
                       "branch": None, "amount": 500.0, "due_date": date.today().isoformat(),
                       "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    for sb in at.selectbox:
        if sb.key == "gx_f_group":
            sb.set_value("Sin agrupar").run()
            break
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any(l.endswith("gasto(s)") for l in labels)


def test_variable_pending_section_groups(run_view, db):
    db.create_expense({"kind": "variable", "name": "Reparación", "category": "Servicios",
                       "branch": "Sucursal 1", "amount": 300.0, "due_date": date.today().isoformat(),
                       "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Total variable pendiente") == "S/ 300.00"
    labels = [e.label for e in at.expander]
    assert any("Servicios" in l for l in labels)


def test_two_stale_dialog_flags_do_not_crash(run_view, db):
    """Regresión: si quedan marcados los dos gates de diálogo (uno se cerró
    haciendo clic afuera), la página no debe reventar con
    StreamlitInvalidLayoutContextError — se muestra uno solo."""
    fx = db.create_fixed_expense({"name": "Alquiler", "category": "Alquiler", "branch": None,
                                  "amount": 3000.0, "pay_day": 5})
    db.ensure_expense_instances()
    exp = db.list_expenses()[0]
    at = run_view(VIEW, role="admin", _fx_dialog={"data": fx}, _gx_manage=exp)
    assert not at.exception


def test_edit_fixed_expense_dialog_shows_end_date(run_view, db):
    db.create_fixed_expense({
        "name": "Cuota préstamo", "category": "Servicios", "branch": None,
        "amount": 900.0, "pay_day": 10, "start_month": "2026-09-01", "end_month": "2028-08-01",
    })
    at = run_view(VIEW, role="admin")
    for b in at.button:
        if b.key and b.key.startswith("fx_edit_"):
            b.click().run()
            break
    # el checkbox de "termina en algún mes" debe salir marcado y la fecha visible
    chk = [c for c in at.checkbox if c.key == "fx_endon"]
    assert chk and chk[0].value is True
    assert any(d.key == "fx_end" for d in at.date_input)


def test_remove_end_date_makes_it_indefinite(db):
    fx = db.create_fixed_expense({
        "name": "Alquiler", "category": "Alquiler", "branch": None,
        "amount": 3000.0, "pay_day": 5, "end_month": "2026-10-01",
    })
    db.update_fixed_expense(fx["id"], {"end_month": None})
    db.ensure_expense_instances()
    periods = sorted({e["period"] for e in db.expenses})
    assert len(periods) == 4  # vuelve a generar mes actual + 3, sin tope


def test_update_fixed_expense_syncs_pending_instances(db):
    from datetime import date

    fx = db.create_fixed_expense({"name": "Alquiler", "category": "Alquiler", "branch": None,
                                  "amount": 3000.0, "pay_day": 5})
    db.ensure_expense_instances()
    # una cuota futura marcada pagada: NO debe cambiar de monto
    fut_paid = next(e for e in db.expenses
                    if e["fixed_expense_id"] == fx["id"] and e["period"] > date.today().strftime("%Y-%m"))
    db.set_expense_status(fut_paid["id"], "pagado", "2026-01-01")

    db.update_fixed_expense(fx["id"], {"name": "Alquiler", "category": "Alquiler",
                                       "branch": None, "amount": 3625.0, "pay_day": 5, "active": True,
                                       "start_month": None, "end_month": None})

    still_pending = [e for e in db.expenses
                     if e["fixed_expense_id"] == fx["id"] and e["status"] == "pendiente"]
    assert still_pending and all(e["amount"] == 3625.0 for e in still_pending)
    assert next(e for e in db.expenses if e["id"] == fut_paid["id"])["amount"] == 3000.0


def test_deactivate_fixed_expense_drops_future_pending(db):
    fx = db.create_fixed_expense({"name": "Publicidad", "category": "Servicios", "branch": None,
                                  "amount": 500.0, "pay_day": 10})
    db.ensure_expense_instances()
    assert len([e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]) >= 3
    db.update_fixed_expense(fx["id"], {"name": "Publicidad", "category": "Servicios", "branch": None,
                                       "amount": 500.0, "pay_day": 10, "active": False,
                                       "start_month": None, "end_month": None})
    assert [e for e in db.expenses if e["fixed_expense_id"] == fx["id"] and e["status"] == "pendiente"] == []


def test_rename_category_cascades(db):
    db.create_fixed_expense({
        "name": "Alquiler local", "category": "Alquiler", "branch": None,
        "amount": 3000.0, "pay_day": 5,
    })
    db.ensure_expense_instances()
    cat_id = next(c["id"] for c in db.expense_categories if c["name"] == "Alquiler")
    db.rename_expense_category(cat_id, "Arriendos")
    assert all(f["category"] != "Alquiler" for f in db.fixed_expenses)
    assert all(e["category"] == "Arriendos" for e in db.expenses)
