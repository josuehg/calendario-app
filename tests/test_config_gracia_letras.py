"""Plazo real de pago de letras, configurable en Configuración (se usa para
ubicar letras en Calendario/Resumen/Presupuesto y decidir cuándo se
consideran de verdad vencidas)."""
from tests.conftest import click

VIEW = "views/6_Configuracion.py"


def _set_number(at, key, value):
    for ni in at.number_input:
        if ni.key == key:
            ni.set_value(value)
            return
    raise AssertionError(f"no se encontró number_input {key!r}")


def test_valores_por_defecto(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    tipico = next(n for n in at.number_input if n.key == "cfg_letra_tipico")
    maximo = next(n for n in at.number_input if n.key == "cfg_letra_max")
    assert tipico.value == 8
    assert maximo.value == 10


def test_guardar_nuevos_plazos(run_view, db):
    at = run_view(VIEW, role="admin")
    _set_number(at, "cfg_letra_tipico", 5)
    _set_number(at, "cfg_letra_max", 15)
    at.run()
    click(at, "Guardar plazos de letras")
    assert not at.exception
    assert db.settings["letra_dias_pago_tipico"] == 5
    assert db.settings["letra_dias_gracia_max"] == 15


def test_maximo_menor_que_tipico_muestra_error(run_view, db):
    at = run_view(VIEW, role="admin")
    _set_number(at, "cfg_letra_tipico", 10)
    _set_number(at, "cfg_letra_max", 5)
    at.run()
    assert any("no puede ser menor" in e.value for e in at.error)
    assert not any(b.label == "Guardar plazos de letras" for b in at.button)
