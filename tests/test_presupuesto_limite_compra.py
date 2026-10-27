"""Límite de compra (fuera de gastos fijos) en Presupuesto — cuánto se puede
comprometer en compras nuevas a proveedores según el promedio de ventas."""
from datetime import date, timedelta

VIEW = "views/5_Presupuesto.py"


def test_sin_ingresos_muestra_aviso(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(c.value) for c in at.caption)
    assert "No hay ingresos registrados" in text


def test_con_ingresos_y_gastos_fijos_muestra_limite(run_view, db):
    for n in range(30):
        d = date.today() - timedelta(days=n)
        db.create_income({"branch": "Sucursal 1", "date": d.isoformat(), "amount": 100.0})
    db.fixed_expenses.append({
        "id": 1, "name": "Alquiler", "category": "Alquiler", "branch": None,
        "amount": 500.0, "pay_day": 5, "frequency": "mensual", "pay_day_2": None,
        "active": True, "start_month": None, "end_month": None, "notes": None,
    })
    at = run_view(VIEW, role="admin", pp_dias_venta=30)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Venta promedio mensual"] == "S/ 3,000.00"
    assert metrics["Gastos fijos mensuales"] == "S/ 500.00"
    assert metrics["🛒 Límite de compra mensual"] == "S/ 2,500.00"
