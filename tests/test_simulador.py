"""Simulador de crédito: cancelar deudas informales con un crédito."""
from datetime import date

from tests.conftest import click

VIEW = "views/12_Simulador.py"

DEUDAS = [
    {"id": "a", "nombre": "China", "saldo": 30000.0, "cuota": 3000.0, "fixed_expense_id": 1},
    {"id": "b", "nombre": "Carmen", "saldo": 100000.0, "cuota": 10000.0, "fixed_expense_id": 2},
]


def test_deudas_del_simulador_usan_la_cuota_del_gasto_fijo(db):
    import utils
    fx = [{"id": 1, "name": "SRA CHINA", "amount": 3000.0}]
    debts = [
        {"id": "a", "creditor": "Sra China", "debt_type": "informal", "balance": 30000, "monthly_payment": 2500,
         "fixed_expense_id": 1, "active": True},
        {"id": "b", "creditor": "BCP", "debt_type": "bancario", "balance": 50000, "monthly_payment": 2000,
         "fixed_expense_id": None, "active": True},
        {"id": "c", "creditor": "Pagada", "debt_type": "informal", "balance": 0, "monthly_payment": 0,
         "fixed_expense_id": None, "active": True},
    ]
    [d] = utils.simulator_debts(debts, fx)
    assert (d["nombre"], d["saldo"], d["cuota"]) == ("SRA CHINA", 30000.0, 3000.0)


def test_simulacion_cancelar_baja_la_cuota_desde_el_mes_siguiente(db):
    import utils
    base = [
        {"mes": "2026-11", "ventas": 100000.0, "fijos": 0.0, "proveedores": 80000.0, "otros": 50000.0},
        {"mes": "2026-12", "ventas": 200000.0, "fijos": 10000.0, "proveedores": 100000.0, "otros": 90000.0},
    ]
    r = utils.simulate_credit(base, DEUDAS, {"a": 30000.0, "b": 50000.0}, caja_inicial=5000.0, credito=220000.0)
    assert r["usado"] == 80000.0 and r["sobra_credito"] == 140000.0
    assert r["cuota_antes"] == 13000.0 and r["cuota_despues"] == 5000.0 and r["ahorro_mensual"] == 8000.0
    assert r["deuda_restante"] == 50000.0
    # Nov: 5000 + 220000 - 80000 + 100000 - 130000 = 115000 (sin cuotas: ya registradas en "otros").
    # Dic: 115000 + 210000 - 190000 - 5000 = 130000.
    assert [s["caja_fin"] for s in r["serie"]] == [115000.0, 130000.0]
    assert r["mes_rojo"] is None and r["mes_minimo"] == "2026-11"


def test_base_excluye_cuotas_de_las_deudas_y_estima_proveedores(db):
    import utils
    events = [
        {"date": "2026-11-05", "amount": 1000.0, "kind": "invoice"},          # atrasado: entra al mes en curso
        {"date": "2026-11-24", "amount": 3000.0, "kind": "expense", "fixed_expense_id": 1},  # mes en curso: se queda
        {"date": "2026-12-24", "amount": 3000.0, "kind": "expense", "fixed_expense_id": 1},  # la pone el simulador
        {"date": "2026-12-10", "amount": 500.0, "kind": "expense", "fixed_expense_id": 9},
        {"date": "2027-01-15", "amount": 20000.0, "kind": "letra"},
    ]
    base = utils.simulation_base(events, [], [{"date": "2026-11-23", "amount": 10000.0}], DEUDAS,
                                 venta_dia=1000.0, compras_mes=50000.0, today="2026-11-11", n_meses=3)
    nov, dic, ene = base
    assert (nov["proveedores"], nov["otros"], nov["fijos"], nov["ventas"]) == (1000.0, 3000.0, 10000.0, 20000.0)
    assert (dic["otros"], dic["proveedores"], dic["ventas"]) == (500.0, 0.0, 31000.0)
    assert ene["proveedores"] == 50000.0  # tercer mes: al menos las compras promedio


def test_compras_promedio(db):
    import utils
    inv = [{"issue_date": "2026-08-10", "amount": 90.0}, {"issue_date": "2026-09-01", "amount": 300.0},
           {"issue_date": "2026-10-20", "amount": 600.0}, {"issue_date": "2026-11-02", "amount": 999.0}]
    assert utils.average_monthly_purchases(inv, "2026-11-11") == 330.0


def test_pagina(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    db.create_debt({"creditor": "Sra Marlene", "debt_type": "informal", "principal": 50000.0, "balance": 50000.0,
                    "monthly_payment": 5000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Crédito usado"] == "S/ 0.00" and m["Cuotas de estas deudas / mes"] == "S/ 8,000.00"
    at = click(at, "Las más chicas")
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Crédito usado"] == "S/ 80,000.00"
    assert m["Cuotas de estas deudas / mes"] == "S/ 0.00"
    assert len(next(d.value for d in at.dataframe if "Caja a fin de mes" in d.value.columns)) == 7


def test_pagina_sin_deudas(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("No hay deudas informales" in i.value for i in at.info)


def test_compras_promedio_ignora_meses_antes_de_usar_la_app(db):
    import utils
    inv = [{"issue_date": "2026-09-05", "amount": 113000.0}, {"issue_date": "2026-10-05", "amount": 114000.0},
           {"issue_date": "2026-11-02", "amount": 16000.0}]
    # Agosto no tiene facturas (aún no se usaba la app): promedio de sep y oct.
    assert utils.average_monthly_purchases(inv, "2026-11-11") == 113500.0
    assert utils.average_monthly_purchases([], "2026-11-11") == 0.0


def test_arranque_y_cuanto_baja_al_mes(db):
    import utils
    base = [
        {"mes": "2026-11", "ventas": 140000.0, "fijos": 10000.0, "proveedores": 106441.73, "otros": 86550.41},
        {"mes": "2026-12", "ventas": 100000.0, "fijos": 0.0, "proveedores": 90000.0, "otros": 30000.0},
        {"mes": "2027-01", "ventas": 100000.0, "fijos": 0.0, "proveedores": 90000.0, "otros": 40000.0},
    ]
    r = utils.simulate_credit(base, DEUDAS, {"a": 30000.0, "b": 96000.0}, caja_inicial=-30000.0, credito=220000.0)
    assert r["caja_arranque"] == 64000.0 and r["sobra_credito"] == 94000.0
    assert r["serie"][0]["caja_fin"] == 21007.86  # el ejemplo de la conversación
    # Dic baja 20000 + cuota restante (400) y ene 30000 + 400: promedio -25400.
    assert r["cambio_mensual_promedio"] == -25400.0
    assert r["mes_rojo"] == "2027-01"


def test_pagina_explica_arranque_y_hasta_cuando_alcanza(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Arrancas con S/ 220,000.00" in m.value for m in at.markdown)
    assert any(b.label == "No cancelar nada" for b in at.button)
    assert not any(b.label in ("Guardar todo", "Limpiar") for b in at.button)


def test_boton_carga_datos_del_sistema(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    hoy = date.today().isoformat()
    db.create_income({"branch": "Sucursal 1", "date": hoy, "amount": 6500.0})
    at = run_view(VIEW, role="admin")
    venta = next(n for n in at.number_input if n.key == "sim_venta")
    assert venta.value == 6500.0
    venta.set_value(9000.0).run()
    assert next(n for n in at.number_input if n.key == "sim_venta").value == 9000.0
    at = click(at, "Cargar datos del sistema")
    assert not at.exception
    assert next(n for n in at.number_input if n.key == "sim_venta").value == 6500.0


def test_inversiones_salen_en_su_mes_y_recuperan_despues(db):
    import utils
    base = [
        {"mes": "2026-11", "ventas": 0.0, "fijos": 0.0, "proveedores": 0.0, "otros": 0.0},
        {"mes": "2026-12", "ventas": 1000.0, "fijos": 0.0, "proveedores": 0.0, "otros": 0.0},
        {"mes": "2027-01", "ventas": 1000.0, "fijos": 0.0, "proveedores": 0.0, "otros": 0.0},
    ]
    inv = [{"monto": 10000.0, "mes": "2026-12", "recupera": 0.0, "mes_recupera": None},
           {"monto": 5000.0, "mes": "2026-12", "recupera": 8000.0, "mes_recupera": "2027-01"}]
    r = utils.simulate_credit(base, [], {}, caja_inicial=0.0, credito=20000.0, inversiones=inv)
    assert [s["inversiones"] for s in r["serie"]] == [0.0, -15000.0, 8000.0]
    assert [s["caja_fin"] for s in r["serie"]] == [20000.0, 6000.0, 15000.0]
    assert (r["total_inversiones"], r["total_recupera"]) == (15000.0, 8000.0)
    # La tendencia no cuenta las inversiones: solo las ventas de 1000 al mes.
    assert r["cambio_mensual_promedio"] == 1000.0


def test_pagina_trae_inversiones_de_ejemplo(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tabla = next(d.value for d in at.dataframe if "Caja a fin de mes" in d.value.columns)
    assert "Inversiones" in tabla.columns
    assert tabla["Inversiones"].iloc[1] == "S/ -15,000.00"


def _serie(*cajas):
    return [{"mes": f"m{k}", "caja_fin": c} for k, c in enumerate(cajas)]


def test_ajuste_sin_rojo_es_cero(db):
    import utils
    a = utils.adjustment_to_stay_positive(_serie(1000.0, 500.0, 200.0))
    assert a == {"compras_mes": 0.0, "venta_mes": 0.0, "venta_dia": 0.0, "extra_inicio": 0.0, "extra_inicio_ventas": 0.0}


def test_ajuste_compras_y_ventas(db):
    import utils
    # Cae 10k al mes desde el mes 2: hasta -30k en el mes 4.
    a = utils.adjustment_to_stay_positive(_serie(20000.0, 10000.0, 0.0, -10000.0, -30000.0))
    # Compras se notan desde el mes 2: el mes 4 tiene 3 meses de ahorro → 10k; el 3, 2 meses → 5k.
    assert a["compras_mes"] == 10000.0 and a["extra_inicio"] == 0.0
    # Ventas desde el mes 1: mes 4 → 30k/4 = 7.5k al mes = 250 por día.
    assert (a["venta_mes"], a["venta_dia"]) == (7500.0, 250.0)


def test_ajuste_pide_plata_ya_si_el_mes_siguiente_queda_en_rojo(db):
    import utils
    a = utils.adjustment_to_stay_positive(_serie(5000.0, -8000.0, -10000.0))
    assert a["extra_inicio"] == 8000.0
    assert a["compras_mes"] == 2000.0  # con los 8k cubiertos, al mes 2 le faltan 2k en 1 mes de ahorro


def test_guardar_y_cargar_escenario(run_view, db):
    d = db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                        "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    next(n for n in at.number_input if n.key == f"sim_pago_{d['id']}").set_value(30000.0)
    next(n for n in at.number_input if n.key == "sim_venta").set_value(7000.0)
    next(t for t in at.text_input if t.label == "Nombre del escenario").set_value("Plan B")
    at = click(at, "Guardar escenario")
    assert not at.exception
    [esc] = db.sim_scenarios
    assert esc["name"] == "Plan B"
    assert esc["data"]["pagos"] == {str(d["id"]): 30000.0} and esc["data"]["sim_venta"] == 7000.0
    assert len(esc["data"]["inversiones"]) == 2

    # Otra sesión: arranca de cero y carga el escenario guardado.
    at = run_view(VIEW, role="admin")
    assert next(n for n in at.number_input if n.key == f"sim_pago_{d['id']}").value == 0.0
    at = next(b for b in at.button if b.label == "Cargar").click().run()
    assert not at.exception
    assert next(n for n in at.number_input if n.key == f"sim_pago_{d['id']}").value == 30000.0
    assert next(n for n in at.number_input if n.key == "sim_venta").value == 7000.0
    assert any("Escenario cargado: Plan B" in s.value for s in at.success)

    at = next(b for b in at.button if b.label == "Eliminar").click().run()
    assert db.sim_scenarios == []


def test_pagina_muestra_meta_para_no_entrar_en_rojo(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    db.create_expense({"name": "Alquiler", "amount": 250000.0, "due_date": date.today().isoformat(),
                       "status": "pendiente", "category": "Alquiler", "branch": "Sucursal 1", "kind": "variable"})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Para que tu caja no entre en rojo" in i.value for i in at.info)


def test_ventanas_de_compra(db):
    import utils
    events = [
        {"date": "2027-01-15", "amount": 101100.0, "kind": "letra"},
        {"date": "2027-02-20", "amount": 8700.0, "kind": "invoice"},
        {"date": "2027-01-05", "amount": 50000.0, "kind": "expense"},  # gastos no cuentan
    ]
    serie = [{"mes": "2026-12", "caja_fin": 1000.0}, {"mes": "2027-01", "caja_fin": 500.0},
             {"mes": "2027-02", "caja_fin": -100.0}]
    inv = [{"issue_date": "2026-11-03", "amount": 16000.0}, {"issue_date": "2026-10-03", "amount": 99.0}]
    v = utils.purchase_windows(events, inv, serie, 113500.0, today="2026-11-11")
    f60, f75, f90 = v["filas"]
    assert (f60["vence"], f60["espacio"], f60["dias_1_10"]) == ("2027-01-10", 12400.0, True)
    assert (f75["vence"], f75["dias_1_10"]) == ("2027-01-25", False)
    # Enero tiene espacio pero febrero (después) queda en rojo en el escenario.
    assert f60["estado"] == "caja"
    assert (f90["vence"], f90["espacio"], f90["estado"]) == ("2027-02-09", 104800.0, "caja")
    assert (v["comprado_este_mes"], v["queda_este_mes"]) == (16000.0, 97500.0)
    # Con una meta más baja, enero se llena.
    v = utils.purchase_windows(events, inv, serie, 95000.0, today="2026-11-11")
    assert v["filas"][0]["estado"] == "lleno" and v["filas"][0]["espacio"] == 0.0


def test_pagina_muestra_ventanas(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tabla = next(d.value for d in at.dataframe if "Si pides hoy a…" in d.value.columns)
    assert list(tabla["Si pides hoy a…"]) == ["60 días", "75 días", "90 días"]
