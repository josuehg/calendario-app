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


def test_proveedores_fijo_mas_nuevas(db):
    import utils
    events = [{"date": "2027-01-15", "amount": 101100.0, "kind": "letra"},
              {"date": "2026-12-15", "amount": 125000.0, "kind": "invoice"}]
    base = utils.simulation_base(events, [], [], [], 0.0, 113500.0, today="2026-11-11", n_meses=4, compras_nuevas={})
    assert [f["prov_registrado"] for f in base] == [0.0, 125000.0, 101100.0, 0.0]
    # Lo que se pida hoy vence desde enero (hoy + 60 días): nov y dic quedan fijos.
    prop = utils.default_new_purchases(base, 113500.0, today="2026-11-11")
    assert prop == {"2027-01": 12400.0, "2027-02": 113500.0}
    # Con un plan propio, proveedores = fijo + lo planeado.
    plan = {"2027-01": 0.0, "2027-02": 90000.0}
    base = utils.simulation_base(events, [], [], [], 0.0, 113500.0, today="2026-11-11", n_meses=4, compras_nuevas=plan)
    assert [f["proveedores"] for f in base] == [0.0, 125000.0, 101100.0, 90000.0]
    # Sin plan, se completa hasta la meta desde el tercer mes (como antes).
    base = utils.simulation_base(events, [], [], [], 0.0, 113500.0, today="2026-11-11", n_meses=4)
    assert [f["proveedores"] for f in base] == [0.0, 125000.0, 113500.0, 113500.0]


def test_ventanas_usan_el_plan(db):
    import utils
    v = utils.purchase_windows([], [], [], 113500.0, today="2026-11-11", plan={"2027-01": 5000.0, "2027-02": 0.0})
    assert [f["espacio"] for f in v["filas"]] == [5000.0, 5000.0, 0.0]
    assert v["filas"][2]["estado"] == "lleno"


def test_escenario_guarda_y_carga_plan_de_proveedores(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    editor = next(d.value for d in at.dataframe if "Compras nuevas que vencen ese mes" in d.value.columns)
    assert list(editor.columns) == ["Mes", "Ya registrado (fijo)", "Compras nuevas que vencen ese mes"]
    next(t for t in at.text_input if t.label == "Nombre del escenario").set_value("Base")
    at = click(at, "Guardar escenario")
    [esc] = db.sim_scenarios
    meses = list(esc["data"]["prov_nuevas"])
    assert meses  # guarda el plan de compras nuevas

    esc["data"]["prov_nuevas"] = {m: 1234.0 for m in meses}
    at = run_view(VIEW, role="admin")
    at = next(b for b in at.button if b.label == "Cargar").click().run()
    assert not at.exception
    editor = next(d.value for d in at.dataframe if "Compras nuevas que vencen ese mes" in d.value.columns)
    assert set(editor["Compras nuevas que vencen ese mes"]) == {1234.0}


def test_venta_promedio_del_mes_actual(db):
    import utils
    oct_ = [{"date": f"2026-10-{d}", "amount": 6000.0} for d in range(26, 32)]
    nov = [{"date": f"2026-11-{d:02d}", "amount": 7000.0} for d in range(1, 11)]
    assert utils.current_month_daily_sales(oct_ + nov, "2026-11-11") == (7000.0, 10, "mes")
    # A principio de mes (menos de 7 días), usa los últimos 30 días.
    prom, dias, base = utils.current_month_daily_sales(oct_ + nov[:3], "2026-11-03")
    assert (prom, dias, base) == (6333.33, 9, "ultimos")


def test_estado_de_deuda_hoy(db):
    import utils
    d = {"id": "a", "nombre": "China", "saldo": 30000.0, "cuota": 3000.0, "fixed_expense_id": 70}
    gastos = [
        {"fixed_expense_id": 70, "due_date": "2026-10-24", "amount": 3000.0, "status": "pagado"},
        {"fixed_expense_id": 70, "due_date": "2026-11-06", "amount": 3000.0, "status": "pendiente"},
        {"fixed_expense_id": 70, "due_date": "2026-12-06", "amount": 3000.0, "status": "pendiente"},
        {"fixed_expense_id": 99, "due_date": "2026-11-01", "amount": 50.0, "status": "pendiente"},
    ]
    e = utils.debt_status_today(d, gastos, "2026-11-11")
    assert (e["vencidas_n"], e["vencidas_monto"], e["dias_atraso"]) == (1, 3000.0, 5)
    assert (e["interes_dia"], e["corte"], e["dias_desde_corte"], e["interes_corrido"]) == (100.0, "2026-11-06", 5, 500.0)
    assert e["cancelar_hoy"] == 33500.0 and e["proxima"] == "2026-12-06"
    # Al día: sin vencidas, el interés corre desde la última cuota pagada.
    gastos[1]["status"] = "pagado"
    e = utils.debt_status_today(d, gastos, "2026-11-11")
    assert (e["vencidas_n"], e["cancelar_hoy"]) == (0, 30500.0)


def test_pdf_del_simulador(db):
    import reporte_pdf
    import utils
    base = [{"mes": "2026-11", "ventas": 1000.0, "fijos": 0.0, "proveedores": 0.0, "prov_nuevas": 0.0, "otros": 0.0},
            {"mes": "2026-12", "ventas": 1000.0, "fijos": 0.0, "proveedores": 5000.0, "prov_nuevas": 5000.0,
             "otros": 0.0}]
    r = utils.simulate_credit(base, DEUDAS, {"a": 30000.0}, -1000.0, 50000.0,
                              [{"concepto": "Odoo", "monto": 100, "mes": "2026-11"}])
    pdf = reporte_pdf.pdf_simulador({
        "nombre": "Plan Ñandú – prueba", "fecha": "12 de noviembre de 2026", "credito": 50000.0, "caja_hoy": -1000.0,
        "venta_dia": 6764.0, "r": r, "deudas": DEUDAS, "pagos": {"a": 30000.0}, "inversiones": [], "ajuste": {},
        "compras_promedio": 113000.0,
    })
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_pagina_ofrece_descargar_pdf(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Descargar PDF" in b.label for b in at.get("download_button"))


def test_inventario_coherente_con_ventas_y_pagos(db):
    import utils
    serie = [
        {"mes": "2026-11", "ventas": 20 * 6000.0, "proveedores": 90000.0},   # faltan 20 de 30 días
        {"mes": "2026-12", "ventas": 31 * 6000.0, "proveedores": 120000.0},
        {"mes": "2027-01", "ventas": 31 * 6000.0, "proveedores": 90000.0},
        {"mes": "2027-02", "ventas": 28 * 6000.0, "proveedores": 60000.0},
    ]
    inv = utils.inventory_projection(serie, 540000.0, 0.5, 6000.0)
    f = inv["filas"]
    # Nov: entra 2/3 de lo que se paga en enero (90k * 20/30), sale 120k * 50%.
    assert (f[0]["entra"], f[0]["sale"], f[0]["inventario"]) == (60000.0, 60000.0, 540000.0)
    # Dic: entra lo que se paga en feb (60k), sale 93k.
    assert (f[1]["entra"], f[1]["sale"], f[1]["inventario"]) == (60000.0, 93000.0, 507000.0)
    # Últimos meses: el último pago planeado.
    assert f[3]["entra"] == 60000.0
    assert inv["dias_hoy"] == 180 and inv["estado"] == "alto"  # 540k / 3k por día
    # Comprando casi nada, cae bajo 60 días.
    poco = [dict(s, proveedores=1000.0) for s in serie]
    assert utils.inventory_projection(poco, 200000.0, 0.5, 6000.0)["estado"] == "bajo"
    assert utils.inventory_projection(serie, 0, 0.5, 6000.0)["filas"] == []


def test_pagina_inventario_y_pdf(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin", sim_inv_hoy=593000.0, sim_venta=6764.0, sim_costo_pct=56.0)
    assert not at.exception
    textos = " ".join(x.value for x in list(at.success) + list(at.warning) + list(at.error))
    assert "días** de inventario" in textos


def _eventos_mes(meses_montos, kind):
    return [{"date": f"{m}-15", "amount": a, "kind": kind} for m, a in meses_montos]


def test_plan_sugerido_cancela_chicas_respetando_colchon(db):
    import utils
    deudas = [
        {"id": "g", "nombre": "Grande", "saldo": 100000.0, "cuota": 10000.0, "fixed_expense_id": None},
        {"id": "c1", "nombre": "Chica 1", "saldo": 10000.0, "cuota": 1000.0, "fixed_expense_id": None},
        {"id": "c2", "nombre": "Chica 2", "saldo": 30000.0, "cuota": 3000.0, "fixed_expense_id": None},
    ]
    meses = ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05"]
    events = _eventos_mes([(m, 150000.0) for m in meses], "expense")
    s = utils.suggest_plan(events, [], [], deudas, venta_dia=6000.0, credito=100000.0, caja_hoy=0.0,
                           inversiones=[], costo_pct=0.5, today="2026-11-11")
    # Consumo 90k, sin stock lento: 15% menos -> 76.5k -> redondeado a 76k (o 77k).
    assert s["compras"] in (76000.0, 77000.0)
    # Cancela las chicas completas (nunca parcial) y la caja no baja de 10k.
    assert set(s["pagos"]) <= {"c1", "c2", "g"}
    assert all(s["pagos"][k] == next(d["saldo"] for d in deudas if d["id"] == k) for k in s["pagos"])
    assert s["r"]["caja_minima"] >= 10000 or not s["pagos"]
    assert "c1" in s["pagos"] or not s["pagos"]  # la más chica va primero
    assert s["razones"]


def test_plan_sugerido_usa_stock_lento_y_no_baja_de_60_dias(db):
    import utils
    s = utils.suggest_plan([], [], [], [], venta_dia=6000.0, credito=0.0, caja_hoy=0.0, inversiones=[],
                           costo_pct=0.5, inv_hoy=500000.0, inv_lento=240000.0, today="2026-11-11")
    # Consumo 90k - (240k / 2 / 6 = 20k) = 70k.
    assert s["compras"] == 70000.0
    poco = utils.suggest_plan([], [], [], [], venta_dia=6000.0, credito=0.0, caja_hoy=0.0, inversiones=[],
                              costo_pct=0.5, inv_hoy=150000.0, inv_lento=600000.0, today="2026-11-11")
    # Con poco inventario, sube las compras para no quedar bajo 60 días.
    assert poco["compras"] > 45000.0


def test_boton_plan_sugerido(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 10000.0, "balance": 10000.0,
                    "monthly_payment": 1000.0, "active": True})
    at = run_view(VIEW, role="admin", sim_caja=50000.0)
    at = click(at, "Plan sugerido")
    assert not at.exception
    assert any("Por qué este plan" in i.value for i in at.info)
    assert any("Plan sugerido cargado" in s.value for s in at.success)


PRESTAMOS = [{"nombre": "Scotiabank", "monto": 700000.0, "cuotas": 36, "cuota": 23259.59, "primera_cuota": "2027-01"},
             {"nombre": "Caja Arequipa", "monto": 100000.0, "cuotas": 24, "cuota": 4877.20, "primera_cuota": "2026-12"}]


def test_calendario_de_renovaciones(db):
    import utils
    deu = [{"id": n, "nombre": n, "saldo": s, "cuota": s / 10} for n, s in
           [("a", 10000.0), ("b", 10000.0), ("c", 10000.0), ("d", 30000.0), ("e", 45000.0), ("f", 50000.0), ("g", 103000.0)]]
    r = utils.renewal_schedule(PRESTAMOS, deu, "2027-03", 3, 8)
    f = r["filas"]
    # Marzo: 3 cuotas de Scotiabank y 4 de Caja Arequipa.
    assert round(f[0]["por_prestamo"]["Scotiabank"]) == 49219 and round(f[0]["por_prestamo"]["Caja Arequipa"]) == 14590
    assert [d["id"] for d in f[0]["canceladas"]] == ["a", "b", "c", "d"]
    # Al renovar el préstamo vuelve a empezar: cada renovación siguiente entrega lo mismo.
    assert round(f[1]["por_prestamo"]["Scotiabank"]) == 49219
    assert [d["id"] for d in f[1]["canceladas"]] == ["e"] and r["cancel_mes"]["g"] == "2028-03"
    assert r["libre_en"] == "2028-03" and f[-1]["interes_liberado"] == 25800.0


def test_proyeccion_deja_de_cobrar_lo_cancelado_con_renovacion(db):
    import utils
    base = [{"mes": m, "ventas": 0.0, "fijos": 0.0, "proveedores": 0.0, "otros": 0.0}
            for m in ("2027-02", "2027-03", "2027-04")]
    r = utils.simulate_credit(base, DEUDAS, {}, 0.0, 0.0, cancel_mes={"a": "2027-03"})
    # Feb y marzo pagan las dos cuotas (3k + 10k); desde abril solo la de Carmen.
    assert [s["cuotas_deudas"] for s in r["serie"]] == [0.0, 13000.0, 10000.0]


def test_pagina_renovaciones_y_pdf(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tabla = next(d.value for d in at.dataframe if "Renovación" in d.value.columns)
    assert "Cancelas" in tabla.columns
    assert any("libre de estas deudas" in s.value for s in at.success)


def test_pdf_grafico_no_se_parte_en_paginas(db):
    import re
    import reporte_pdf
    import utils
    base = [{"mes": f"2027-{m:02d}", "ventas": 1000.0, "fijos": 0.0, "proveedores": 0.0, "prov_nuevas": 0.0,
             "otros": 0.0} for m in range(1, 8)]
    muchas = [{"id": f"x{i}", "nombre": f"Deuda con un nombre bastante largo número {i}", "saldo": 1000.0,
               "cuota": 100.0} for i in range(40)]
    r = utils.simulate_credit(base, muchas, {}, 0.0, 0.0)
    pdf = reporte_pdf.pdf_simulador({
        "nombre": "Largo", "fecha": "hoy", "credito": 0.0, "caja_hoy": 0.0, "venta_dia": 100.0, "r": r,
        "deudas": muchas, "pagos": {}, "inversiones": [{"concepto": f"Inversión {i}", "monto": 10, "mes": "2027-01"}
                                                       for i in range(12)], "ajuste": {},
    })
    paginas = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
    assert paginas <= 3


def test_por_que_desaparece_si_cambias_el_plan(run_view, db):
    d = db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 10000.0, "balance": 10000.0,
                        "monthly_payment": 1000.0, "active": True})
    at = run_view(VIEW, role="admin", sim_caja=50000.0)
    at = click(at, "Plan sugerido")
    assert any("Por qué este plan" in i.value for i in at.info)
    campo = next(n for n in at.number_input if n.key == f"sim_pago_{d['id']}")
    campo.set_value(0.0 if campo.value else 5000.0).run()
    assert not any("Por qué este plan" in i.value for i in at.info)


def test_proyeccion_larga_usa_plantillas_y_respeta_fin_de_prestamos(db):
    import utils
    fx = [{"id": 1, "name": "Alquiler", "amount": 1000.0, "pay_day": 5, "active": True, "start_month": "2026-01-01",
           "end_month": None},
          {"id": 2, "name": "Banco", "amount": 500.0, "pay_day": 5, "active": True, "start_month": "2026-01-01",
           "end_month": "2027-08-01"}]
    r = utils.long_projection([], fx, [], [], {}, {}, caja_hoy=0.0, credito=0.0, inversiones=[], venta_dia=0.0,
                              costo_pct=0.5, inv_hoy=0.0, compras_plan=0.0, today="2026-11-11", n_meses=12)
    s = {x["mes"]: x for x in r["serie"]}
    # Hasta mayo hay cuotas generadas (aquí no hay eventos: 0); después, desde plantillas.
    assert s["2027-05"]["otros"] == 0.0
    assert s["2027-06"]["otros"] == 1500.0 and s["2027-08"]["otros"] == 1500.0
    assert s["2027-09"]["otros"] == 1000.0  # el banco ya terminó
    assert len(r["serie"]) == 12


def test_proyeccion_larga_mejoras_suben_la_caja_y_renovacion_baja_intereses(db):
    import utils
    deu = [{"id": "a", "nombre": "A", "saldo": 10000.0, "cuota": 1000.0, "fixed_expense_id": None}]
    args = dict(events=[], fixed_expenses=[], ingresos_esperados=[], deudas=deu, pagos={},
                cancel_mes={"a": "2027-03"}, caja_hoy=0.0, credito=0.0, inversiones=[], venta_dia=1000.0,
                costo_pct=0.5, inv_hoy=60000.0, compras_plan=10000.0, today="2026-11-11", n_meses=8)
    base = utils.long_projection(**args)
    mej = utils.long_projection(**args, crec_anual=0.1, margen_pts=3, ahorro_mes=2000, liquidacion_mes=5000,
                                inv_lento=20000)
    s = {x["mes"]: x for x in base["serie"]}
    assert s["2027-03"]["intereses"] == 1000.0 and s["2027-04"]["intereses"] == 0.0
    assert mej["serie"][-1]["caja"] > base["serie"][-1]["caja"]
    assert base["stock_normal_en"] is not None  # con 60 días de stock y compras bajas, llega a lo normal


def test_pagina_informe_de_gestion(run_view, db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("informe de gestión" in b.label for b in at.get("download_button"))
    labels = {m.label for m in at.metric}
    assert "Caja más baja si seguimos igual" in labels and "Caja más baja con mejoras" in labels


def test_pdf_gestion(db):
    import reporte_gestion
    import utils
    args = dict(events=[], fixed_expenses=[], ingresos_esperados=[], deudas=DEUDAS, pagos={}, cancel_mes={},
                caja_hoy=10000.0, credito=0.0, inversiones=[], venta_dia=1000.0, costo_pct=0.5, inv_hoy=90000.0,
                compras_plan=10000.0, today="2026-11-11", n_meses=14)
    pdf = reporte_gestion.pdf_gestion({
        "nombre": "Plan", "fecha": "hoy", "base": utils.long_projection(**args),
        "mejoras": utils.long_projection(**args, crec_anual=0.05, margen_pts=3, ahorro_mes=8000),
        "params": {"crec_anual": 0.05, "margen_pts": 3, "ahorro_mes": 8000, "liquidacion_mes": 15000},
        "renov": None, "inv_hoy": 90000.0, "inv_lento": 40000.0, "inv_balanceo": 8000.0,
        "compras_promedio": 20000.0, "venta_dia": 1000.0,
    })
    assert pdf[:4] == b"%PDF"


def test_mezcla_de_plazos_y_pago_por_plazo(db):
    import utils
    inv = [{"issue_date": "2026-10-01", "due_date": "2026-12-30", "amount": 60.0, "doc_type": "credito"},   # 90
           {"issue_date": "2026-10-05", "due_date": "2026-12-04", "amount": 30.0, "doc_type": "credito"},   # 60
           {"issue_date": "2026-10-10", "due_date": None, "amount": 10.0, "doc_type": "contado"},
           {"issue_date": "2026-05-01", "due_date": "2026-07-30", "amount": 999.0, "doc_type": "credito"}]  # viejo
    assert utils.purchase_term_mix(inv, "2026-11-11") == {0: 0.1, 60: 0.3, 90: 0.6}
    meses = ["m0", "m1", "m2", "m3", "m4"]
    compras = {"m1": 100.0}
    # Comprado en m1: 60 días -> se paga en m3; 90 -> m4; 75 -> mitad m3 y mitad m4.
    assert utils._pago_de_compras(compras, meses, 3, {60: 1.0}) == 100.0
    assert utils._pago_de_compras(compras, meses, 4, {90: 1.0}) == 100.0
    assert utils._pago_de_compras(compras, meses, 3, {75: 1.0}) == 50.0
    assert utils._pago_de_compras(compras, meses, 4, {75: 1.0}) == 50.0


def test_proyeccion_larga_respeta_el_plan_de_pagos_del_simulador(db):
    import utils
    args = dict(events=[], fixed_expenses=[], ingresos_esperados=[], deudas=[], pagos={}, cancel_mes={},
                caja_hoy=0.0, credito=0.0, inversiones=[], venta_dia=1000.0, costo_pct=0.5, inv_hoy=900000.0,
                compras_plan=20000.0, today="2026-11-11", n_meses=8, mezcla={90: 1.0})
    r = utils.long_projection(**args, pagos_plan={"2027-01": 5000.0, "2027-02": 7000.0})
    s = {x["mes"]: x for x in r["serie"]}
    assert s["2027-01"]["compras_pagadas"] == 5000.0 and s["2027-02"]["compras_pagadas"] == 7000.0
    # Después del plan, se paga a 90 días lo comprado 3 meses antes (20k al mes).
    assert s["2027-03"]["compras_pagadas"] == 20000.0


def test_desglose_de_mejoras(db):
    import utils
    args = dict(events=[], fixed_expenses=[], ingresos_esperados=[], deudas=[], pagos={}, cancel_mes={},
                caja_hoy=0.0, credito=0.0, inversiones=[], venta_dia=1000.0, costo_pct=0.5, inv_hoy=90000.0,
                compras_plan=15000.0, today="2026-11-11", n_meses=10, inv_lento=20000.0)
    dg = utils.improvements_breakdown(args, 0.05, 3.0, 2000.0, 0.0)
    nombres = [f["palanca"] for f in dg["filas"]]
    assert "Liquidar stock lento" not in nombres  # en 0: no se muestra
    reprog = next(f for f in dg["filas"] if f["palanca"] == "Reprogramar y gastos")
    # 2,000 al mes desde el 3er mes de 10: 8 meses = 16,000; la mitad, 8,000.
    assert reprog["total"] == 16000.0 and reprog["total_mitad"] == 8000.0
    assert dg["total"] >= max(f["total"] for f in dg["filas"])
    assert dg["filas"] == sorted(dg["filas"], key=lambda f: -f["total"])
