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
