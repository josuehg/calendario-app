"""Página Compras del día."""
from datetime import date, timedelta

VIEW = "views/13_Compras.py"


def test_pagina_sin_escenarios_usa_meta_a_mano(run_view, db):
    hoy = date.today().isoformat()
    db.create_invoice({"vendor": "Lab", "invoice_number": "F1", "branch": "Sucursal 1", "amount": 30000.0,
                       "issue_date": hoy, "due_date": hoy, "doc_type": "credito", "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Ya pedido (facturas del mes)"] == "S/ 30,000.00"
    tabla = at.dataframe[0].value
    assert list(tabla["Plazo del proveedor"]) == ["30 días", "60 días", "75 días", "90 días"]


def _ventas(db, monto_dia):
    hoy = date.today()
    for k in range(1, 8):
        db.create_income({"branch": "Sucursal 1", "date": (hoy - timedelta(days=k)).isoformat(), "amount": monto_dia})


def test_pagina_toma_la_meta_del_plan_guardado(run_view, db):
    db.create_sim_scenario({"name": "PLAN FINAL", "data": {"sim_compras": 81000.0}})
    _ventas(db, 10000.0)
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Meta del mes"] == "S/ 81,000.00"
    assert any("Hoy conviene pedir" in s.value for s in at.success)


def test_ventana_de_emergencia_con_dias_de_gracia(run_view, db):
    db.save_settings({"letra_dias_gracia_max": 8})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tabla = next(d.value for d in at.dataframe if "Se pagaría" in d.value.columns)
    assert list(tabla["Plazo"]) == ["60 + 8 días", "75 + 8 días", "90 + 8 días"]


def test_la_caja_limita_lo_que_puedes_pedir(run_view, db):
    """Meta con espacio pero el mes no tiene caja: no debe decir que puedes pedir todo."""
    db.create_sim_scenario({"name": "PLAN FINAL", "data": {"sim_compras": 81000.0}})
    _ventas(db, 1000.0)  # ~30k al mes
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tabla = next(d.value for d in at.dataframe if "Puedes pedir" in d.value.columns and "Plazo del proveedor" in d.value.columns)
    assert all(e in ("🟠 Limita la caja", "🔴 La caja no alcanza") for e in tabla["Estado"])
    assert not any("S/ 81,000.00" == x for x in tabla["Puedes pedir"])


def test_caja_que_sobra_es_el_neto_proyectado_al_reves(db):
    import utils
    events = [{"date": "2027-02-05", "amount": 50000.0, "kind": "expense"},
              {"date": "2027-03-01", "amount": 99999.0, "kind": "expense"}]
    fijos = [{"date": "2027-02-23", "amount": 10000.0}]
    sobra = utils.month_cash_room(events, [], fijos, "2027-02", today="2026-11-14")
    assert sobra == -40000.0  # sin ventas registradas: 10k fijos - 50k pagos
    assert utils.with_cash_limit(66000.0, sobra) == 0.0
    assert utils.with_cash_limit(66000.0, 22946.55) == 22946.55
    assert utils.with_cash_limit(10000.0, 22946.55) == 10000.0


def test_plan_quita_cuotas_de_deudas_canceladas(db):
    import utils
    deudas = [{"id": 1, "nombre": "Carmen", "saldo": 100000.0, "cuota": 10000.0, "fixed_expense_id": "fx1"},
              {"id": 2, "nombre": "China", "saldo": 30000.0, "cuota": 3000.0, "fixed_expense_id": "fx2"}]
    plan = utils.plan_debt_cuotas({"pagos": {"1": 100000.0, "2": 15000.0}}, deudas)
    assert plan == {"fx1": {"factor": 0.0, "cancel_mes": None}, "fx2": {"factor": 0.5, "cancel_mes": None}}
    events = [
        {"date": "2026-11-20", "amount": 10000.0, "kind": "expense", "fixed_expense_id": "fx1"},  # mes en curso: igual
        {"date": "2027-02-05", "amount": 10000.0, "kind": "expense", "fixed_expense_id": "fx1"},  # cancelada: sale
        {"date": "2027-02-05", "amount": 3000.0, "kind": "expense", "fixed_expense_id": "fx2"},   # mitad
        {"date": "2027-02-05", "amount": 8000.0, "kind": "letra"},
    ]
    out = utils.apply_plan_cuotas(events, plan, today="2026-11-14")
    assert [e["amount"] for e in out] == [10000.0, 1500.0, 8000.0]
    # Con renovación: se paga ese mes y deja de cobrarse desde el siguiente.
    out = utils.apply_plan_cuotas(
        [{"date": m, "amount": 3000.0, "kind": "expense", "fixed_expense_id": "fx2"} for m in ("2027-02-05", "2027-03-05")],
        {"fx2": {"factor": 1.0, "cancel_mes": "2027-02"}}, today="2026-11-14")
    assert [e["date"] for e in out] == ["2027-02-05"]


def test_pagina_usa_el_plan_para_la_caja(run_view, db):
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Prestamos Usu", "amount": 10300.0, "day": 5,
                                  "active": True, "start_date": date.today().isoformat()})
    d = db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "principal": 103000.0, "balance": 103000.0,
                        "monthly_payment": 10300.0, "active": True, "fixed_expense_id": fx["id"]})
    db.create_sim_scenario({"name": "PLAN ALFIN", "data": {"sim_compras": 81000.0, "pagos": {str(d["id"]): 103000.0}}})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("según PLAN ALFIN" in c.value and "Sra Carmen" in c.value for c in at.caption)


def test_caja_disponible_arrastra_el_credito_y_las_compras_del_plan(db):
    import utils
    # Sin ventas: cada mes futuro falta 20k (gastos); el crédito da 100k de colchón.
    events = [{"date": m, "amount": 20000.0, "kind": "expense"} for m in ("2026-12-05", "2027-01-05", "2027-02-05")]
    disp = utils.cash_available_by_month(events, [], [], 30000.0, 100000.0,
                                         ["2026-11", "2026-12", "2027-01", "2027-02"], today="2026-11-14")
    assert disp["2026-11"] == 100000.0               # mes en curso: sin compras del plan
    assert disp["2026-12"] == 80000.0                # 100k - 20k gastos
    assert disp["2027-01"] == 30000.0                # 80k - 30k compras de dic - 20k gastos
    assert disp["2027-02"] == -20000.0               # 30k - 30k compras de ene - 20k gastos
    assert utils.with_cash_limit(30000.0, disp["2027-02"]) == 0.0


def _plan_con_caja(db, incluido):
    ayer = (date.today() - timedelta(days=1)).isoformat()
    db.save_settings({"caja_saldo_inicial": 300000.0, "caja_saldo_inicial_fecha": ayer,
                      "caja_credito_incluido": incluido})
    db.create_sim_scenario({"name": "PLAN FINAL", "data": {"sim_compras": 81000.0, "sim_credito": 237000.0}})


def test_credito_ya_depositado_no_se_cuenta_dos_veces(run_view, db):
    _plan_con_caja(db, 237000.0)
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("ya incluye el crédito" in c.value and "aún no entra" not in c.value for c in at.caption)


def test_credito_que_aun_no_entra_se_suma_en_la_vista_del_plan(run_view, db):
    _plan_con_caja(db, 0.0)
    at = run_view(VIEW, role="admin")
    assert any("crédito del plan que aún no entra S/ 237,000.00" in c.value for c in at.caption)
    # Día a día: solo la caja real, sin el crédito ni nada del plan.
    next(t for t in at.toggle if t.key == "cd_segun_plan").set_value(False).run()
    assert not at.exception
    assert any("Día a día" in c.value and "aún no entra" not in c.value for c in at.caption)


def test_colchon_se_resta_y_queda_guardado(run_view, db):
    _plan_con_caja(db, 237000.0)
    at = run_view(VIEW, role="admin")
    antes = next(d.value for d in at.dataframe if "Caja disponible ese mes" in d.value.columns)
    next(n for n in at.number_input if n.key == "cd_colchon").set_value(50000.0).run()
    assert not at.exception
    assert db.settings["compras_colchon"] == 50000.0
    despues = next(d.value for d in at.dataframe if "Caja disponible ese mes" in d.value.columns)
    assert list(antes["Caja disponible ese mes"]) != list(despues["Caja disponible ese mes"])
    assert any("colchón S/ 50,000.00" in c.value for c in at.caption)
