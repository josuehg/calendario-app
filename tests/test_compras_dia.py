"""Página Compras del día."""
from datetime import date

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


def test_pagina_toma_la_meta_del_plan_guardado(run_view, db):
    db.create_sim_scenario({"name": "PLAN FINAL", "data": {"sim_compras": 81000.0}})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Meta del mes"] == "S/ 81,000.00"
    assert any("Hoy conviene pedir" in s.value for s in at.success)
