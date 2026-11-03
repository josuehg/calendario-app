"""Registrar/editar/eliminar ingresos en la página Ingresos."""
from datetime import date

from tests.conftest import click

VIEW = "views/10_Ingresos.py"


def _llenar(at, montos):
    hoy = date.today().isoformat()
    for ni in at.number_input:
        for branch, monto in montos.items():
            if ni.key == f"inc_monto_{hoy}_{branch}":
                ni.set_value(monto)
    return at


def test_registra_varias_sucursales_de_una_vez(run_view, db):
    at = _llenar(run_view(VIEW, role="admin"), {"Sucursal 1": 1500.0, "Sucursal 2": 980.5})
    at = click(at, "Registrar ingresos")
    assert not at.exception
    assert {r["branch"]: r["amount"] for r in db.incomes} == {"Sucursal 1": 1500.0, "Sucursal 2": 980.5}
    assert all(r["source"] == "app" and r["date"] == date.today().isoformat() for r in db.incomes)


def test_sucursal_vacia_no_se_registra_y_cero_si(run_view, db):
    # Un local cerrado ese día vendió 0 — es un dato válido (evita el aviso
    # de "falta registrar" en el reporte diario); vacío es "aún no lo tengo".
    at = _llenar(run_view(VIEW, role="admin"), {"Sucursal 1": 0.0})
    at = click(at, "Registrar ingresos")
    assert not at.exception
    assert [(r["branch"], r["amount"]) for r in db.incomes] == [("Sucursal 1", 0.0)]


def test_sin_montos_avisa_y_no_registra(run_view, db):
    at = click(run_view(VIEW, role="admin"), "Registrar ingresos")
    assert not at.exception
    assert db.incomes == []
    assert any("al menos una sucursal" in w.value for w in at.warning)


def test_sucursal_ya_registrada_no_se_pide_de_nuevo(run_view, db):
    hoy = date.today().isoformat()
    db.create_income({"branch": "Sucursal 1", "date": hoy, "amount": 700.0})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert not any(ni.key == f"inc_monto_{hoy}_Sucursal 1" for ni in at.number_input)
    assert any("Ya registrado: S/ 700.00" in c.value for c in at.caption)
    at = _llenar(at, {"Sucursal 2": 200.0})
    at = click(at, "Registrar ingresos")
    assert not at.exception
    assert sorted(r["branch"] for r in db.incomes) == ["Sucursal 1", "Sucursal 2"]


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
