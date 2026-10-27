"""Registrar/editar/eliminar ingresos en la página Ingresos."""
from datetime import date

from tests.conftest import click

VIEW = "views/10_Ingresos.py"


def test_registrar_ingreso_lo_guarda(run_view, db):
    at = run_view(VIEW, role="admin")
    for sb in at.selectbox:
        if sb.key == "inc_branch":
            sb.set_value("Sucursal 2").run()
    for ni in at.number_input:
        if ni.key == "inc_monto":
            ni.set_value(1500.0).run()
    click(at, "Registrar")
    assert len(db.incomes) == 1
    row = db.incomes[0]
    assert row["branch"] == "Sucursal 2" and row["amount"] == 1500.0
    assert row["source"] == "app"


def test_registrar_con_monto_cero_lo_guarda(run_view, db):
    # Un local cerrado ese día vendió 0 — es un dato válido (evita el aviso
    # de "falta registrar" en el reporte diario), no un error.
    at = run_view(VIEW, role="admin")
    at = click(at, "Registrar")
    assert not at.exception
    assert at.error == []
    assert len(db.incomes) == 1
    assert db.incomes[0]["amount"] == 0.0


def test_historial_filtra_por_sucursal(run_view, db):
    db.create_income({"branch": "Sucursal 1", "date": "2026-09-01", "amount": 100.0})
    db.create_income({"branch": "Sucursal 2", "date": "2026-09-02", "amount": 200.0})
    at = run_view(VIEW, role="admin")
    for sb in at.selectbox:
        if sb.key == "inc_f_branch":
            at = sb.set_value("Sucursal 1").run()
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Sucursal 1" in text and "Sucursal 2" not in text


def test_editar_ingreso_actualiza_monto(run_view, db):
    inc = db.create_income({"branch": "Sucursal 1", "date": "2026-09-01", "amount": 100.0})
    at = run_view(VIEW, role="admin")
    at = click(at, "Editar")
    assert not at.exception
    for ni in at.number_input:
        if ni.key == "inc_ed_monto":
            ni.set_value(250.0).run()
    at = click(at, "Guardar")
    assert not at.exception
    assert db.incomes[0]["amount"] == 250.0


def test_eliminar_ingreso_lo_borra(run_view, db):
    db.create_income({"branch": "Sucursal 1", "date": "2026-09-01", "amount": 100.0})
    at = run_view(VIEW, role="admin")
    at = click(at, "Eliminar")
    assert not at.exception
    at = click(at, "Sí, eliminar")
    assert not at.exception
    assert db.incomes == []
