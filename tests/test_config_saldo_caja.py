"""Caja de partida: se corrige en el Simulador (✏️ Corregir caja), ya no en
Configuración. Desde ese punto la app suma ventas y resta pagos registrados."""
from datetime import date, timedelta

from tests.conftest import click

SIM = "views/12_Simulador.py"


def _con_deuda(db):
    db.create_debt({"creditor": "Sra China", "debt_type": "informal", "principal": 30000.0, "balance": 30000.0,
                    "monthly_payment": 3000.0, "active": True})


def test_configuracion_ya_no_tiene_saldo_inicial(run_view, db):
    at = run_view("views/6_Configuracion.py", role="admin")
    assert not at.exception
    assert not any(n.key == "cfg_saldo_inicial" for n in at.number_input)


def test_corregir_caja_desde_el_simulador(run_view, db):
    _con_deuda(db)
    ayer = (date.today() - timedelta(days=1)).isoformat()
    at = run_view(SIM, role="admin")
    next(n for n in at.number_input if n.key == "sim_credito").set_value(237000.0).run()
    next(n for n in at.number_input if n.key == "sim_cc_banco").set_value(300000.0)
    next(n for n in at.number_input if n.key == "sim_cc_bcp").set_value(20000.0)
    at = click(at, "Guardar caja")
    assert not at.exception
    assert db.settings["caja_saldo_inicial"] == 43000.0  # 300k - 20k BCP - 237k del crédito
    assert db.settings["caja_saldo_inicial_fecha"] == ayer
    assert next(n for n in at.number_input if n.key == "sim_caja").value == 43000.0
    assert any("Caja corregida" in s.value for s in at.success)

    # Al día siguiente: lo vendido hoy se suma solo.
    db.create_income({"branch": "Sucursal 1", "date": date.today().isoformat(), "amount": 5000.0})
    at = run_view(SIM, role="admin")
    assert next(n for n in at.number_input if n.key == "sim_caja").value == 48000.0


def test_corregir_caja_sin_credito_en_banco(run_view, db):
    _con_deuda(db)
    at = run_view(SIM, role="admin")
    next(n for n in at.number_input if n.key == "sim_cc_banco").set_value(50000.0)
    next(c for c in at.checkbox if c.key == "sim_cc_cred").uncheck()
    at = click(at, "Guardar caja")
    assert db.settings["caja_saldo_inicial"] == 50000.0
