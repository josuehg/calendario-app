"""Indicadores de venta de la página Ingresos (utils.income_indicators)."""
from datetime import date

VIEW = "views/10_Ingresos.py"


def _inc(fecha, branch, monto):
    return {"date": fecha, "branch": branch, "amount": monto}


def test_totales_promedio_y_comparacion(db):
    import utils
    incomes = [
        _inc("2026-11-01", "A", 100.0), _inc("2026-11-02", "A", 300.0),
        _inc("2026-11-01", "B", 50.0), _inc("2026-11-02", "B", 0.0),  # B cerró el 2
        _inc("2026-10-30", "A", 200.0),  # periodo anterior (30-31 oct)
    ]
    ind = utils.income_indicators(incomes, ["A", "B"], "2026-11-01", "2026-11-02")
    assert ind["total"] == 450.0
    assert ind["promedio_diario"] == 225.0
    assert ind["mejor_dia"] == ("2026-11-02", 300.0)
    assert ind["total_anterior"] == 200.0 and ind["variacion"] == 125.0
    a, b = ind["por_sucursal"]
    assert (a["branch"], a["total"], a["promedio"], a["participacion"]) == ("A", 400.0, 200.0, 88.9)
    # El día cerrado (0) no baja el promedio de B.
    assert (b["promedio"], b["dias_abiertos"], b["dias_cerrados"], b["dias_sin_registrar"]) == (50.0, 1, 1, 0)
    assert b["variacion"] is None  # sin venta en el periodo anterior


def test_dias_sin_registrar(db):
    import utils
    ind = utils.income_indicators([_inc("2026-11-01", "A", 10.0)], ["A"], "2026-11-01", "2026-11-03")
    assert ind["por_sucursal"][0]["dias_sin_registrar"] == 2


def test_periodos(db):
    import utils
    hoy = date(2026, 11, 8)
    assert utils.income_period("Últimos 7 días", hoy) == ("2026-11-02", "2026-11-08")
    assert utils.income_period("Este mes", hoy) == ("2026-11-01", "2026-11-08")
    assert utils.income_period("Mes pasado", hoy) == ("2026-10-01", "2026-10-31")


def test_pagina_muestra_indicadores(run_view, db):
    import utils
    # La página mide el periodo con la fecha de Perú; date.today() en el
    # servidor de CI (UTC) ya es "mañana" desde las 7 pm de Perú.
    hoy = utils.today_lima().isoformat()
    db.create_income({"branch": "Sucursal 1", "date": hoy, "amount": 1500.0})
    db.create_income({"branch": "Sucursal 2", "date": hoy, "amount": 500.0})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Venta total"] == "S/ 2,000.00"
    assert metricas["Promedio por día"] == "S/ 2,000.00"
    tabla = at.dataframe[0].value
    assert list(tabla["Sucursal"][:2]) == ["Sucursal 1", "Sucursal 2"]
    assert tabla["% del total"].iloc[0] == "75.0%"
