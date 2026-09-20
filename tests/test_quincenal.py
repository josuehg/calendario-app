"""Gastos fijos quincenales (dos pagos al mes, ej. planilla quincenal)."""
from datetime import date

import pytest

from tests.conftest import click, widget

VIEW = "views/7_Gastos.py"
FIJOS = "🔁 Gastos fijos"


def _goto(at, section):
    for r in at.radio:
        if r.key == "gx_section":
            return r.set_value(section).run()
    raise AssertionError("no se encontró el radio de sección (gx_section)")


@pytest.fixture
def utils_mod(db):
    import utils
    return utils


# ---------- lógica pura ----------

def _fx(**kw):
    base = dict(id=1, name="Planilla", category="Planilla", branch=None, amount=5000.0,
               pay_day=15, frequency="mensual", pay_day_2=None,
               start_month=None, end_month=None, notes=None)
    base.update(kw)
    return base


def test_mensual_generates_one_row_per_month(utils_mod):
    today = date(2026, 9, 10)
    rows = utils_mod.fixed_expense_rows_to_create([_fx()], [], today, months_ahead=2)
    assert [r["period"] for r in rows] == ["2026-09", "2026-10", "2026-11"]
    assert all(r["due_date"].endswith("-15") for r in rows)


def test_quincenal_generates_two_rows_per_month(utils_mod):
    today = date(2026, 9, 1)
    fx = _fx(frequency="quincenal", pay_day=15, pay_day_2=30)
    rows = utils_mod.fixed_expense_rows_to_create([fx], [], today, months_ahead=1)
    periods = sorted(r["period"] for r in rows)
    assert periods == ["2026-09-Q1", "2026-09-Q2", "2026-10-Q1", "2026-10-Q2"]
    due_dates = sorted(r["due_date"] for r in rows if r["period"] == "2026-09-Q1" or r["period"] == "2026-09-Q2")
    assert due_dates == ["2026-09-15", "2026-09-30"]
    # cada cuota mantiene el monto por pago, no el doble
    assert all(r["amount"] == 5000.0 for r in rows)


def test_quincenal_payday_31_in_short_month_clamps(utils_mod):
    today = date(2026, 1, 20)  # que arranque en enero para llegar a febrero
    fx = _fx(frequency="quincenal", pay_day=15, pay_day_2=31)
    rows = utils_mod.fixed_expense_rows_to_create([fx], [], today, months_ahead=1)
    feb = [r for r in rows if r["period"] == "2026-02-Q2"]
    assert feb and feb[0]["due_date"] == "2026-02-28"


def test_quincenal_idempotent(utils_mod):
    today = date(2026, 9, 1)
    fx = _fx(frequency="quincenal", pay_day=15, pay_day_2=30)
    first = utils_mod.fixed_expense_rows_to_create([fx], [], today, months_ahead=0)
    again = utils_mod.fixed_expense_rows_to_create([fx], first, today, months_ahead=0)
    assert again == []


def test_occurrences_per_month(utils_mod):
    assert utils_mod.occurrences_per_month(_fx(frequency="mensual")) == 1
    assert utils_mod.occurrences_per_month(_fx(frequency="quincenal", pay_day_2=None)) == 1
    assert utils_mod.occurrences_per_month(_fx(frequency="quincenal", pay_day_2=30)) == 2


# ---------- db: generación real + edición ----------

def test_db_generates_two_pending_per_month_for_quincenal(db):
    fx = db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                                  "amount": 5000.0, "pay_day": 15, "frequency": "quincenal", "pay_day_2": 30})
    db.ensure_expense_instances(months_ahead=0)
    rows = [e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert len(rows) == 2
    assert sorted(e["due_date"][-2:] for e in rows) == ["15", "30"]


def test_switch_mensual_to_quincenal_repurposes_existing_row(db):
    fx = db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                                  "amount": 5000.0, "pay_day": 15})
    db.ensure_expense_instances(months_ahead=0)
    assert len([e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]) == 1

    db.update_fixed_expense(fx["id"], {"name": "Planilla", "category": "Planilla", "branch": None,
                                       "amount": 5000.0, "frequency": "quincenal",
                                       "pay_day": 15, "pay_day_2": 30, "active": True,
                                       "start_month": None, "end_month": None})
    rows = [e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert len(rows) == 1
    assert rows[0]["period"].endswith("-Q1")

    db.ensure_expense_instances(months_ahead=0)
    rows = [e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert len(rows) == 2
    assert {r["period"][-2:] for r in rows} == {"Q1", "Q2"}


def test_switch_quincenal_to_mensual_drops_second_row(db):
    fx = db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                                  "amount": 5000.0, "pay_day": 15, "frequency": "quincenal", "pay_day_2": 30})
    db.ensure_expense_instances(months_ahead=0)
    assert len([e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]) == 2

    db.update_fixed_expense(fx["id"], {"name": "Planilla", "category": "Planilla", "branch": None,
                                       "amount": 5000.0, "frequency": "mensual",
                                       "pay_day": 15, "pay_day_2": None, "active": True,
                                       "start_month": None, "end_month": None})
    rows = [e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert len(rows) == 1
    assert not rows[0]["period"].endswith(("Q1", "Q2"))


# ---------- UI ----------

def test_create_quincenal_fixed_expense_via_dialog(run_view, db):
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    click(at, "➕ Nuevo gasto fijo")
    for ti in at.text_input:
        if ti.key == "fx_name":
            ti.set_value("Planilla quincenal").run()
            break
    for ni in at.number_input:
        if ni.key == "fx_amount":
            ni.set_value(5000.0).run()
            break
    for r in at.radio:
        if r.key == "fx_freq":
            r.set_value("Quincenal").run()
            break
    for ni in at.number_input:
        if ni.key == "fx_day":
            ni.set_value(15).run()
            break
    for ni in at.number_input:
        if ni.key == "fx_day2":
            ni.set_value(30).run()
            break
    click(at, "Guardar")
    assert not at.exception
    fx = next(f for f in db.fixed_expenses if f["name"] == "Planilla quincenal")
    assert fx["frequency"] == "quincenal"
    assert fx["pay_day"] == 15 and fx["pay_day_2"] == 30


def test_same_two_paydays_rejected(run_view, db):
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    click(at, "➕ Nuevo gasto fijo")
    for ti in at.text_input:
        if ti.key == "fx_name":
            ti.set_value("Planilla mala").run()
            break
    for ni in at.number_input:
        if ni.key == "fx_amount":
            ni.set_value(5000.0).run()
            break
    for r in at.radio:
        if r.key == "fx_freq":
            r.set_value("Quincenal").run()
            break
    for ni in at.number_input:
        if ni.key == "fx_day2":
            ni.set_value(1).run()  # igual al día 1 por defecto de fx_day
            break
    click(at, "Guardar")
    assert any("no pueden ser el mismo" in e.value for e in at.error)
    assert not db.fixed_expenses


def test_fijos_row_shows_both_paydays(run_view, db):
    db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                             "amount": 5000.0, "pay_day": 15, "frequency": "quincenal", "pay_day_2": 30})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    assert not at.exception
    md = " ".join(str(m.value) for m in at.markdown)
    assert "Días 15 y 30" in md


def test_editar_gasto_fijo_quincenal_precarga_frecuencia_y_dias(run_view, db):
    db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                             "amount": 5000.0, "pay_day": 15, "frequency": "quincenal", "pay_day_2": 30})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    click(at, "Editar")
    assert not at.exception
    freq = next(r for r in at.radio if r.key == "fx_freq")
    assert freq.value == "Quincenal"
    day1 = next(ni for ni in at.number_input if ni.key == "fx_day")
    day2 = next(ni for ni in at.number_input if ni.key == "fx_day2")
    assert day1.value == 15 and day2.value == 30


def test_monthly_total_counts_quincenal_twice(run_view, db):
    db.create_fixed_expense({"name": "Planilla", "category": "Planilla", "branch": None,
                             "amount": 5000.0, "pay_day": 15, "frequency": "quincenal", "pay_day_2": 30})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Total mensual comprometido") == "S/ 10,000.00"
