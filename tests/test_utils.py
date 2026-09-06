from datetime import date

import pytest


@pytest.fixture
def utils(db):
    import utils as u
    return u


# ---------- fechas y moneda ----------

def test_add_days_and_fmt(utils):
    assert utils.add_days("2026-01-30", 30) == "2026-03-01"
    assert utils.fmt_short("2026-09-05") == "05/09/26"
    assert utils.fmt_short(None) == "—"


def test_start_of_week_is_monday(utils):
    # 2026-09-05 es sábado -> lunes de esa semana es 2026-08-31
    assert utils.start_of_week("2026-09-05") == "2026-08-31"


def test_money(utils):
    assert utils.money(1712.5) == "S/ 1,712.50"
    assert utils.money(None) == "S/ 0.00"


# ---------- día de pago recortado a fin de mes ----------

@pytest.mark.parametrize("y,m,day,expected", [
    (2026, 2, 31, 28),   # febrero no bisiesto
    (2028, 2, 31, 29),   # febrero bisiesto
    (2026, 4, 31, 30),   # abril tiene 30
    (2026, 1, 15, 15),   # normal
    (2026, 12, 5, 5),
])
def test_due_day_for_month(utils, y, m, day, expected):
    assert utils.due_day_for_month(y, m, day) == expected


# ---------- generación de gastos fijos ----------

def _fx(**kw):
    base = dict(id=1, name="Alquiler", category="Alquiler", branch=None,
               amount=3000.0, pay_day=5, start_month=None, end_month=None, notes=None)
    base.update(kw)
    return base


def test_fixed_expense_rows_count_and_dates(utils):
    today = date(2026, 9, 10)
    rows = utils.fixed_expense_rows_to_create([_fx()], [], today, months_ahead=3)
    assert [r["period"] for r in rows] == ["2026-09", "2026-10", "2026-11", "2026-12"]
    assert all(r["due_date"].endswith("-05") for r in rows)
    assert all(r["kind"] == "fijo" and r["status"] == "pendiente" for r in rows)


def test_fixed_expense_skips_existing(utils):
    today = date(2026, 9, 10)
    existing = [{"fixed_expense_id": 1, "period": "2026-09"}]
    rows = utils.fixed_expense_rows_to_create([_fx()], existing, today, months_ahead=2)
    assert [r["period"] for r in rows] == ["2026-10", "2026-11"]


def test_fixed_expense_respects_start_and_end_month(utils):
    today = date(2026, 9, 1)
    fx = _fx(start_month="2026-10-01", end_month="2026-11-01")
    rows = utils.fixed_expense_rows_to_create([fx], [], today, months_ahead=6)
    assert [r["period"] for r in rows] == ["2026-10", "2026-11"]


def test_fixed_expense_payday_31_clamps(utils):
    today = date(2026, 1, 5)
    rows = utils.fixed_expense_rows_to_create([_fx(pay_day=31)], [], today, months_ahead=2)
    assert [r["due_date"] for r in rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]


# ---------- eventos de pago ----------

def _inv(**kw):
    base = dict(id="i1", branch="Sucursal 1", vendor="Prov", invoice_number="F1",
                doc_type="credito", amount=100.0, due_date="2026-09-20", status="pendiente")
    base.update(kw)
    return base


def test_events_from_invoices(utils):
    ev = utils.get_payment_events([_inv()], [], [], True)
    assert len(ev) == 1 and ev[0]["kind"] == "invoice" and ev[0]["amount"] == 100.0


def test_events_skip_paid_and_canjeada(utils):
    invs = [_inv(id="a", status="pagada"), _inv(id="b", status="canjeada"), _inv(id="c")]
    ev = utils.get_payment_events(invs, [], [], True)
    assert {e["ref_id"] for e in ev} == {"c"}


def test_events_track_contado_filter(utils):
    invs = [_inv(id="a", doc_type="contado"), _inv(id="b", doc_type="credito")]
    assert len(utils.get_payment_events(invs, [], [], True)) == 2
    assert {e["ref_id"] for e in utils.get_payment_events(invs, [], [], False)} == {"b"}


def test_events_from_expenses_only_pending(utils):
    exp = [
        {"id": "e1", "kind": "fijo", "name": "Alquiler", "category": "Alquiler",
         "branch": None, "amount": 3000.0, "due_date": "2026-09-05", "status": "pendiente"},
        {"id": "e2", "kind": "variable", "name": "Reparación", "category": "Servicios",
         "branch": "Sucursal 2", "amount": 200.0, "due_date": "2026-09-10", "status": "pagado"},
        {"id": "e3", "kind": "fijo", "name": "Planilla", "category": "Planilla",
         "branch": None, "amount": 8000.0, "due_date": "2026-09-30", "status": "omitido"},
    ]
    ev = utils.get_payment_events([], [], [], True, exp)
    assert [e["ref_id"] for e in ev] == ["e1"]
    assert ev[0]["kind"] == "expense" and ev[0]["branch"] == "General"
    assert "Alquiler" in ev[0]["label"]


def test_compute_stats_and_weekly_buckets(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-09-07")
    events = [
        {"date": "2026-09-01", "amount": 50.0},    # vencido
        {"date": "2026-09-07", "amount": 20.0},    # hoy
        {"date": "2026-09-10", "amount": 30.0},    # esta semana
        {"date": "2026-12-01", "amount": 100.0},   # lejos
    ]
    s = utils.compute_stats(events)
    assert s["vencido"] == 50.0 and s["hoy"] == 20.0
    assert s["esta_semana"] == 50.0  # hoy + 10-sep
    assert s["total_pendiente"] == 200.0
    buckets = utils.weekly_buckets(events, weeks_ahead=13)
    assert sum(b["count"] for b in buckets) >= 3
