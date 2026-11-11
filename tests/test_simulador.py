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
    assert len(at.dataframe[0].value) == 7


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
