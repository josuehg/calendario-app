"""Saldo inicial de caja, configurable en Configuración (se usa junto con
Ingresos y los pagos registrados para calcular el saldo de caja real y lo
disponible para comprometer en Presupuesto)."""
from datetime import date

from tests.conftest import click

VIEW = "views/6_Configuracion.py"


def test_valores_por_defecto_son_cero_sin_fecha(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    saldo = next(n for n in at.number_input if n.key == "cfg_saldo_inicial")
    assert saldo.value == 0.0


def test_guardar_saldo_inicial(run_view, db):
    at = run_view(VIEW, role="admin")
    for ni in at.number_input:
        if ni.key == "cfg_saldo_inicial":
            ni.set_value(5000.0)
    for di in at.date_input:
        if di.key == "cfg_saldo_fecha":
            di.set_value(date(2026, 10, 1))
    at.run()
    click(at, "Guardar saldo inicial")
    assert not at.exception
    assert db.settings["caja_saldo_inicial"] == 5000.0
    assert db.settings["caja_saldo_inicial_fecha"] == "2026-10-01"
