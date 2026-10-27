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


def test_df_to_xlsx_bytes_roundtrips(utils):
    import pandas as pd
    df = pd.DataFrame({"Proveedor": ["Prov A", "Prov B"], "Monto": [100.0, 200.5]})
    raw = utils.df_to_xlsx_bytes(df, "Hoja1")
    assert isinstance(raw, bytes) and len(raw) > 0
    import io
    back = pd.read_excel(io.BytesIO(raw), sheet_name="Hoja1")
    assert back["Proveedor"].tolist() == ["Prov A", "Prov B"]
    assert back["Monto"].tolist() == [100.0, 200.5]


def test_start_of_week_is_monday(utils):
    # 2026-09-05 es sábado -> lunes de esa semana es 2026-08-31
    assert utils.start_of_week("2026-09-05") == "2026-08-31"


def test_money(utils):
    assert utils.money(1712.5) == "S/ 1,712.50"
    assert utils.money(None) == "S/ 0.00"


def test_to_lima_date_str(utils):
    # 02:00 UTC del 8-sep = 21:00 hora Perú del 7-sep (cruza medianoche hacia atrás)
    assert utils.to_lima_date_str("2026-09-08T02:00:00+00:00") == "2026-09-07"
    assert utils.to_lima_date_str("2026-09-08T06:00:00+00:00") == "2026-09-08"
    assert utils.to_lima_date_str("2026-09-08T02:00:00") == "2026-09-07"  # sin zona: se asume UTC
    assert utils.to_lima_date_str(None) == ""


def test_today_lima_is_utc_minus_5(utils, monkeypatch):
    from datetime import datetime, timezone

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 8, 2, 30, tzinfo=timezone.utc)  # 21:30 del 7-sep en Perú

    monkeypatch.setattr(utils, "datetime", _FixedDatetime)
    assert utils.today_lima().isoformat() == "2026-09-07"


def test_fmt_time(utils):
    assert utils.fmt_time("2026-09-07T19:32:05") == "14:32"           # sin zona: se asume UTC -> Perú
    assert utils.fmt_time("2026-09-07T19:32:05+00:00") == "14:32"     # UTC -> Perú (-5)
    assert utils.fmt_time("2026-09-08T02:00:00+00:00") == "21:00"     # cruza medianoche hacia atrás
    assert utils.fmt_time(None) == "—"
    assert utils.fmt_time("basura") == "—"


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


# ---------- historial de pagados (get_paid_events) ----------

def test_paid_events_solo_incluye_lo_pagado_con_fecha_de_pago(utils):
    invs = [
        _inv(id="a", status="pagada", paid_at="2026-09-18"),
        _inv(id="b", status="pendiente"),
        _inv(id="c", status="canjeada"),
    ]
    ev = utils.get_paid_events(invs, [], [])
    assert [e["ref_id"] for e in ev] == ["a"]
    assert ev[0]["date"] == "2026-09-18"


def test_paid_events_de_letras_usa_fecha_pago(utils):
    letras = [
        {"id": "L1", "estado": "pagada", "fecha_pago": "2026-09-19", "monto": 500.0,
         "numero": "001", "vendor": "Prov", "branch": "Sucursal 1", "paid_by": "Josue"},
        {"id": "L2", "estado": "pendiente", "fecha_pago": None, "monto": 100.0,
         "numero": "002", "vendor": "Prov", "branch": "Sucursal 1"},
    ]
    ev = utils.get_paid_events([], letras, [])
    assert [e["ref_id"] for e in ev] == ["L1"]
    assert ev[0]["date"] == "2026-09-19" and ev[0]["paid_by"] == "Josue"


def test_paid_events_de_gastos_usa_paid_at(utils):
    exp = [
        {"id": "e1", "kind": "fijo", "name": "Alquiler", "category": "Alquiler",
         "branch": None, "amount": 3000.0, "status": "pagado", "paid_at": "2026-09-05"},
        {"id": "e2", "kind": "variable", "name": "Reparación", "category": "Servicios",
         "branch": "Sucursal 2", "amount": 200.0, "status": "pendiente", "paid_at": None},
    ]
    ev = utils.get_paid_events([], [], exp)
    assert [e["ref_id"] for e in ev] == ["e1"]
    assert ev[0]["date"] == "2026-09-05" and ev[0]["branch"] == "General"


# ---------- vencimientos sospechosos ----------

def _vendor(**kw):
    base = dict(id=1, name="Prov", doc_type="credito", term_days=30)
    base.update(kw)
    return base


def test_suspicious_flags_due_date_mismatch(utils):
    invs = [_inv(vendor="Prov", issue_date="2026-09-01", due_date="2026-09-01")]
    out = utils.find_suspicious_due_dates(invs, [_vendor()])
    assert len(out) == 1
    assert out[0]["expected_due_date"] == "2026-10-01"
    assert out[0]["vendor_term_days"] == 30


def test_suspicious_ignores_matching_due_date(utils):
    invs = [_inv(vendor="Prov", issue_date="2026-09-01", due_date="2026-10-01")]
    assert utils.find_suspicious_due_dates(invs, [_vendor()]) == []


def test_suspicious_ignores_non_pending_or_contado(utils):
    invs = [
        _inv(vendor="Prov", issue_date="2026-09-01", due_date="2026-09-01", status="pagada"),
        _inv(vendor="Prov", issue_date="2026-09-01", due_date="2026-09-01", doc_type="contado"),
    ]
    assert utils.find_suspicious_due_dates(invs, [_vendor()]) == []


def test_suspicious_ignores_vendor_without_configured_term(utils):
    invs = [_inv(vendor="Sin Plazo", issue_date="2026-09-01", due_date="2026-09-01")]
    assert utils.find_suspicious_due_dates(invs, [_vendor(name="Sin Plazo", doc_type="contado", term_days=None)]) == []


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


# ---------- balance semanal (Presupuesto) ----------

def test_weekly_balance_tracks_debido_pagado_y_saldo(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-09-21")
    invoices = [
        {"doc_type": "credito", "due_date": "2026-09-01", "amount": 100.0, "status": "pendiente", "paid_at": None},
        {"doc_type": "credito", "due_date": "2026-09-08", "amount": 50.0, "status": "pagada", "paid_at": "2026-09-10"},
        {"doc_type": "contado", "due_date": "2026-09-05", "amount": 999.0, "status": "pendiente", "paid_at": None},
    ]
    letras = [{"fecha_vencimiento": "2026-09-15", "monto": 30.0, "estado": "pendiente", "fecha_pago": None}]
    expenses = [{"due_date": "2026-09-20", "amount": 20.0, "status": "pendiente", "paid_at": None}]

    buckets = utils.weekly_balance(invoices, letras, expenses, weeks_back=8)
    assert buckets
    assert sum(b["debido"] for b in buckets) == 200.0   # 100 + 50 + 30 + 20, sin el contado
    assert sum(b["pagado"] for b in buckets) == 50.0
    assert buckets[-1]["saldo"] == 150.0                # 200 - 50, acumulado hasta la última semana


def test_weekly_balance_respects_weeks_back_limit(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-12-01")
    invoices = [{"doc_type": "credito", "due_date": "2026-01-05", "amount": 10.0, "status": "pendiente", "paid_at": None}]
    buckets = utils.weekly_balance(invoices, [], [], weeks_back=4)
    assert len(buckets) == 4


def test_weekly_balance_empty_when_no_data(utils):
    assert utils.weekly_balance([], [], []) == []


def test_weekly_balance_ubica_letra_en_fecha_esperada_no_en_vencimiento(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-09-21")
    letras = [{"fecha_vencimiento": "2026-09-01", "monto": 100.0, "estado": "pendiente", "fecha_pago": None}]
    buckets = utils.weekly_balance([], letras, [], weeks_back=8, letra_dias_pago_tipico=8)
    semana_del_09_09 = next(b for b in buckets if b["start"] <= "2026-09-09" <= b["end"])
    assert semana_del_09_09["debido"] == 100.0   # 01 + 8 días = 09, no el 01


# ---------- saldo de caja (compute_cash_balance) ----------

def test_cash_balance_sin_movimientos_es_el_saldo_inicial(utils):
    caja = utils.compute_cash_balance([], [], [], [], saldo_inicial=1000.0, saldo_inicial_fecha="2026-09-01")
    assert caja["saldo_actual"] == 1000.0
    assert caja["comprometido"] == 0.0
    assert caja["disponible"] == 1000.0


def test_cash_balance_suma_ingresos_despues_de_la_fecha_semilla(utils):
    incomes = [
        {"date": "2026-09-01", "amount": 500.0},  # mismo día del saldo inicial: no cuenta
        {"date": "2026-09-05", "amount": 300.0},
    ]
    caja = utils.compute_cash_balance([], [], [], incomes, saldo_inicial=1000.0, saldo_inicial_fecha="2026-09-01")
    assert caja["saldo_actual"] == 1300.0


def test_cash_balance_resta_egresos_ya_pagados_despues_de_la_fecha(utils):
    invoices = [
        {"status": "pagada", "paid_at": "2026-09-10", "amount": 200.0},
        {"status": "pagada", "paid_at": "2026-08-20", "amount": 999.0},  # antes de la semilla: no cuenta
        {"status": "pendiente", "amount": 50.0},  # no pagada: no resta del saldo
    ]
    letras = [{"estado": "pagada", "fecha_pago": "2026-09-12", "monto": 80.0}]
    expenses = [{"status": "pagado", "paid_at": "2026-09-15", "amount": 30.0}]
    caja = utils.compute_cash_balance(invoices, letras, expenses, [], saldo_inicial=1000.0, saldo_inicial_fecha="2026-09-01")
    assert caja["saldo_actual"] == 1000.0 - 200.0 - 80.0 - 30.0


def test_cash_balance_comprometido_es_todo_lo_pendiente_sin_importar_fecha(utils):
    invoices = [{"status": "pendiente", "amount": 100.0}, {"status": "pagada", "paid_at": "2026-09-01", "amount": 999.0}]
    letras = [{"estado": "pendiente", "monto": 50.0}]
    expenses = [{"status": "pendiente", "amount": 25.0}, {"status": "pagado", "paid_at": "2026-09-01", "amount": 999.0}]
    caja = utils.compute_cash_balance(invoices, letras, expenses, [], saldo_inicial=0.0, saldo_inicial_fecha=None)
    assert caja["comprometido"] == 175.0


def test_cash_balance_disponible_negativo_si_se_debe_mas_de_lo_que_hay(utils):
    invoices = [{"status": "pendiente", "amount": 5000.0}]
    caja = utils.compute_cash_balance(invoices, [], [], [], saldo_inicial=100.0, saldo_inicial_fecha="2026-09-01")
    assert caja["disponible"] == 100.0 - 5000.0


# ---------- límite de compra (purchase_limit) ----------

def test_average_daily_income_solo_cuenta_el_rango(utils):
    incomes = [
        {"date": "2026-09-01", "amount": 100.0},   # fuera de los últimos 3 días
        {"date": "2026-09-03", "amount": 60.0},
        {"date": "2026-09-04", "amount": 30.0},
    ]
    avg = utils.average_daily_income(incomes, days_back=3, today="2026-09-04")
    assert avg == 30.0  # (60 + 30) / 3 días (01 queda fuera del rango 02-04)


def test_average_daily_income_sin_datos_es_cero(utils):
    assert utils.average_daily_income([], days_back=30, today="2026-09-04") == 0.0


def test_purchase_limit_resta_gastos_fijos_del_promedio_de_ventas(utils):
    incomes = [{"date": "2026-09-01", "amount": 100.0}, {"date": "2026-09-10", "amount": 3000.0}]
    fixed = [_fx(id=1, amount=500.0, frequency="mensual"),      # 500/mes
             _fx(id=2, amount=200.0, frequency="quincenal", pay_day_2=20)]  # 400/mes
    limite = utils.purchase_limit(incomes, fixed, days_back=30, today="2026-09-10")
    assert limite["venta_diaria"] == round((100.0 + 3000.0) / 30, 2)
    assert limite["gastos_fijos_mensuales"] == 900.0
    assert limite["limite_mensual"] == round(limite["venta_mensual"] - 900.0, 2)


def test_purchase_limit_ignora_gastos_fijos_inactivos(utils):
    fixed = [_fx(id=1, amount=500.0, active=False), _fx(id=2, amount=100.0, active=True)]
    limite = utils.purchase_limit([], fixed, days_back=30, today="2026-09-10")
    assert limite["gastos_fijos_mensuales"] == 100.0


# ---------- cuánto comprometer con un proveedor a X días (max_new_purchase) ----------

def test_max_new_purchase_usa_la_semana_mas_ajustada_no_el_dia_final(utils):
    # Sin nada comprometido y con venta positiva, el saldo solo crece con el
    # tiempo -> la semana más ajustada del camino es la primera (la que
    # acumuló menos días de venta), no el día final del plazo.
    today = "2026-09-10"
    fin_primera_semana = utils.add_days(utils.start_of_week(today), 6)
    dias_primera_semana = (date.fromisoformat(fin_primera_semana) - date.fromisoformat(today)).days
    r = utils.max_new_purchase([], saldo_actual=1000.0, venta_diaria=50.0, term_days=60, today=today)
    assert r["fecha_vence"] == "2026-11-09"
    assert r["semana_mas_ajustada"] == fin_primera_semana
    assert r["proyectado"] == 1000.0 + 50.0 * dias_primera_semana
    assert r["maximo"] == r["proyectado"]


def test_max_new_purchase_resta_lo_que_vence_antes_o_en_esa_fecha(utils):
    # Con venta_diaria=0, lo comprometido solo puede crecer semana a semana
    # (nunca se compensa con más venta) -> la semana más ajustada siempre es
    # la última (fecha_vence), con todo lo comprometido ya incluido.
    events = [
        {"date": "2026-11-01", "amount": 2000.0},   # antes de que venza (09-11): resta
        {"date": "2026-11-09", "amount": 500.0},     # mismo día: resta
        {"date": "2026-11-10", "amount": 999.0},     # un día después: no resta
    ]
    r = utils.max_new_purchase(events, saldo_actual=1000.0, venta_diaria=0.0, term_days=60, today="2026-09-10")
    assert r["semana_mas_ajustada"] == r["fecha_vence"]
    assert r["comprometido_antes"] == 2500.0
    assert r["proyectado"] == 1000.0 - 2500.0


def test_max_new_purchase_nunca_es_negativo(utils):
    r = utils.max_new_purchase([], saldo_actual=-500.0, venta_diaria=0.0, term_days=30, today="2026-09-10")
    assert r["proyectado"] == -500.0
    assert r["maximo"] == 0.0


def test_max_new_purchase_detecta_bache_antes_del_vencimiento_final(utils):
    # Un pago grande cae bastante antes del día final del plazo: esa semana
    # debe salir como la más ajustada, aunque para el día final el saldo ya
    # se haya "recuperado" acumulando más venta.
    today = "2026-09-10"
    fecha_bache = utils.add_days(today, 50)
    events = [{"date": fecha_bache, "amount": 5000.0}]
    r = utils.max_new_purchase(events, saldo_actual=1000.0, venta_diaria=100.0, term_days=60, today=today)
    proyectado_dia_final = 1000.0 + 100.0 * 60 - 5000.0
    assert r["semana_mas_ajustada"] != r["fecha_vence"]
    assert r["proyectado"] < proyectado_dia_final
