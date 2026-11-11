"""Ingresos fijos mensuales (comisiones BCP): esperados, caja, simulador y páginas."""
from datetime import date

from tests.conftest import click

BCP = {"name": "Comisiones BCP", "amount": 10000.0, "day_from": 13, "day_to": 23, "start_month": "2026-11"}


def test_esperados_por_mes_hasta_confirmar(db):
    import utils
    fi = db.create_fixed_income(dict(BCP))
    esp = utils.fixed_income_expected([fi], [], today="2026-11-11", months_ahead=2)
    assert [(e["period"], e["date"], e["date_from"]) for e in esp] == [
        ("2026-11", "2026-11-23", "2026-11-13"),
        ("2026-12", "2026-12-23", "2026-12-13"),
        ("2027-01", "2027-01-23", "2027-01-13"),
    ]
    assert not esp[0]["atrasado"]
    # Confirmado noviembre, ya no se espera; y pasado el 23 sin confirmar, atrasado.
    rec = [{"fixed_income_id": fi["id"], "period": "2026-11", "date": "2026-11-20", "amount": 9800.0}]
    assert [e["period"] for e in utils.fixed_income_expected([fi], rec, "2026-11-11", 1)] == ["2026-12"]
    assert utils.fixed_income_expected([fi], [], "2026-11-24", 0)[0]["atrasado"]
    # Desactivado: nada.
    assert utils.fixed_income_expected([{**fi, "active": False}], [], "2026-11-11") == []


def test_dia_recortado_a_fin_de_mes(db):
    import utils
    fi = db.create_fixed_income({**BCP, "day_from": 28, "day_to": 31, "start_month": "2027-02"})
    assert utils.fixed_income_expected([fi], [], "2027-02-01", 0)[0]["date"] == "2027-02-28"


def test_recibido_suma_a_caja(db):
    import utils
    rec = [{"date": "2026-11-20", "amount": 9800.0}, {"date": "2026-10-01", "amount": 5.0}]
    caja = utils.compute_cash_balance([], [], [], [], saldo_inicial=100.0, saldo_inicial_fecha="2026-11-01",
                                      fixed_receipts=rec)
    assert caja["saldo_actual"] == 9900.0


def test_simulador_cuenta_ingreso_esperado_desde_su_semana(db):
    import utils
    pago = [{"date": "2026-11-16", "amount": 5000.0}]
    sin = utils.max_new_purchase(pago, 1000.0, 0.0, 30, today="2026-11-11")
    con = utils.max_new_purchase(pago, 1000.0, 0.0, 30, today="2026-11-11",
                                 ingresos_esperados=[{"date": "2026-11-23", "amount": 10000.0}])
    # La semana del pago (antes de que llegue la comisión) sigue siendo el límite.
    assert sin["maximo"] == con["maximo"] == 0.0
    assert con["proyectado"] == -4000.0
    pago_tarde = [{"date": "2026-11-30", "amount": 5000.0}]
    con = utils.max_new_purchase(pago_tarde, 1000.0, 0.0, 30, today="2026-11-11",
                                 ingresos_esperados=[{"date": "2026-11-23", "amount": 10000.0}])
    assert con["maximo"] == 1000.0


def test_pagina_confirma_recibido(run_view, db):
    hoy = date.today()
    db.create_fixed_income({**BCP, "start_month": hoy.isoformat()[:7]})
    at = run_view("views/10_Ingresos.py", role="admin")
    assert not at.exception
    assert any("Comisiones BCP" in m.value for m in at.markdown)
    at = click(at, "✅ Llegó")
    at.number_input(key="fi_rec_monto").set_value(9850.0)
    at = next(b for b in at.button if b.label == "Guardar").click().run()
    assert not at.exception
    [r] = db.fixed_income_receipts
    assert (r["period"], r["amount"], r["date"]) == (hoy.isoformat()[:7], 9850.0, hoy.isoformat())
    assert not any(b.label == "✅ Llegó" for b in at.button)
    # No se mezcla con las ventas de los locales.
    assert db.incomes == []


def test_pagina_agrega_ingreso_fijo(run_view, db):
    at = run_view("views/10_Ingresos.py", role="admin")
    nombre = next(w for w in at.text_input if w.label == "Nombre")
    nombre.set_value("Comisiones BCP")
    next(w for w in at.number_input if w.label == "Monto aproximado (S/)").set_value(10000.0)
    next(w for w in at.number_input if w.label == "Suele llegar desde el día").set_value(13)
    next(w for w in at.number_input if w.label == "Hasta el día").set_value(23)
    at = click(at, "Agregar ingreso fijo")
    assert not at.exception
    [f] = db.fixed_incomes
    assert (f["name"], f["amount"], f["day_from"], f["day_to"]) == ("Comisiones BCP", 10000.0, 13, 23)


def test_calendario_muestra_ingreso_esperado(run_view, db):
    hoy = date.today()
    db.create_fixed_income({**BCP, "day_from": 28, "day_to": 28, "start_month": hoy.isoformat()[:7]})
    at = run_view("views/4_Calendario.py", role="admin")
    assert not at.exception
    assert any("💵 Comisiones BCP" in m.value for m in at.markdown)


def test_calendario_cifras_de_ingresos_fijos_y_neto(run_view, db):
    hoy = date.today()
    mes = hoy.isoformat()[:7]
    db.create_fixed_income({**BCP, "day_from": 28, "day_to": 28, "start_month": mes})
    db.create_expense({"name": "Alquiler", "amount": 15000.0, "due_date": f"{mes}-27", "status": "pendiente",
                       "category": "Alquiler", "branch": "Sucursal 1", "kind": "variable"})
    at = run_view("views/4_Calendario.py", role="admin")
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["💵 Ingresos fijos del mes"] == "S/ 10,000.00"
    assert m["Neto del mes"] == "S/ 5,000.00"
    assert "💰 Ventas registradas del mes" not in m


def test_calendario_muestra_ventas_y_recibidos_con_filtro(run_view, db):
    hoy = date.today().isoformat()
    fi = db.create_fixed_income({**BCP, "start_month": hoy[:7]})
    db.create_fixed_income_receipt({"fixed_income_id": fi["id"], "name": fi["name"], "period": hoy[:7],
                                    "date": hoy, "amount": 9850.0})
    db.create_income({"branch": "Sucursal 1", "date": hoy, "amount": 1200.0})
    at = run_view("views/4_Calendario.py", role="admin")
    assert not any("💰 Ventas S/" in x.value for x in at.markdown)
    at = run_view("views/4_Calendario.py", role="admin", cal_f_ventas=True)
    assert not at.exception
    textos = " ".join(x.value for x in at.markdown)
    assert "💵✅ Comisiones BCP S/ 9,850.00 recibido" in textos
    assert "💰 Ventas S/ 1,200.00 · 1/3 locales" in textos
    m = {x.label: x.value for x in at.metric}
    assert m["💰 Ventas registradas del mes"] == "S/ 1,200.00"
    assert m["💵 Ingresos fijos del mes"] == "S/ 9,850.00"


def test_calendario_registra_ventas(run_view, db):
    hoy = date.today().isoformat()
    at = run_view("views/4_Calendario.py", role="admin")
    at = click(at, "💰 Registrar ventas")
    campos = [ni for ni in at.number_input if (ni.key or "").startswith(f"calv_monto_{hoy}_")]
    assert len(campos) == 3
    campos[0].set_value(800.0)
    campos[1].set_value(0.0)
    at = click(at, "Guardar ingresos")
    assert not at.exception
    assert sorted((r["branch"], r["amount"]) for r in db.incomes) == [("Sucursal 1", 800.0), ("Sucursal 2", 0.0)]
    assert any("Guardado: 2 nuevo(s)" in s.value for s in at.success)


def test_entradas_esperadas_del_mes(db):
    import utils
    incomes = [
        {"date": "2026-11-09", "amount": 3000.0}, {"date": "2026-11-09", "amount": 1000.0},
        {"date": "2026-11-10", "amount": 6000.0},
        {"date": "2026-11-11", "amount": 2000.0},  # hoy ya registrado: no cuenta como día restante
    ]
    esperados = [
        {"date": "2026-11-23", "amount": 10000.0},
        {"date": "2026-11-05", "amount": 500.0},   # ya debió llegar: no se cuenta
        {"date": "2026-12-23", "amount": 10000.0},  # otro mes
    ]
    e = utils.month_expected_inflows(incomes, esperados, "2026-11", today="2026-11-11")
    # Promedio solo entre días con registro: (4000 + 6000 + 2000) / 3.
    assert e["promedio_diario"] == 4000.0
    assert e["dias_restantes"] == 19  # 12..30 nov
    assert e["venta_esperada"] == 76000.0
    assert e["fijos_por_llegar"] == 10000.0
    assert e["total"] == 86000.0
    # Mes futuro: todos sus días; mes pasado: nada.
    assert utils.month_expected_inflows(incomes, esperados, "2026-12", "2026-11-11")["dias_restantes"] == 31
    assert utils.month_expected_inflows(incomes, esperados, "2026-10", "2026-11-11")["total"] == 0.0


def test_calendario_neto_proyectado(run_view, db):
    at = run_view("views/4_Calendario.py", role="admin")
    assert not at.exception
    m = {x.label: x for x in at.metric}
    assert "📈 Neto proyectado" in m
