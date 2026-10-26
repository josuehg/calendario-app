"""Editar (monto/fecha) y Eliminar directo desde el diálogo del día en
Calendario, junto al botón Pagado ya existente."""
from datetime import date

from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _seed_invoice(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })


# ---------- editar ----------

def test_dia_muestra_boton_editar(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Editar" for b in at.button)


def test_editar_precarga_monto_y_fecha(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    assert not at.exception
    ni = next(n for n in at.number_input if n.key == "cal_edit_monto")
    di = next(d for d in at.date_input if d.key == "cal_edit_fecha")
    assert ni.value == 100.0
    assert di.value == date(2020, 1, 15)


def test_guardar_edicion_actualiza_factura(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(250.0)
            break
    for di in at.date_input:
        if di.key == "cal_edit_fecha":
            di.set_value(date(2020, 1, 20))
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.invoices[0]["amount"] == 250.0
    assert db.invoices[0]["due_date"] == "2020-01-20"


def test_editar_letra_actualiza_monto_y_vencimiento(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-15",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(480.0)
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.letras[0]["monto"] == 480.0


def test_editar_gasto_actualiza_monto(run_view, db):
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler",
                       "branch": "Sucursal 1", "amount": 1000.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    for ni in at.number_input:
        if ni.key == "cal_edit_monto":
            ni.set_value(1200.0)
            break
    click(at, "Guardar")
    assert not at.exception
    assert db.expenses[0]["amount"] == 1200.0


def test_cancelar_edicion_no_cambia_nada(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Editar")
    click(at, "Cancelar")
    assert not at.exception
    assert db.invoices[0]["amount"] == 100.0
    assert at.session_state["_cal_day"] == "2020-01-15"


# ---------- eliminar ----------

def test_dia_muestra_boton_eliminar(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    assert any(b.label == "Eliminar" for b in at.button)


def test_eliminar_pide_confirmacion(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "no se puede deshacer" in warns
    assert db.invoices   # todavía no se borró


def test_confirmar_eliminar_borra_factura(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.invoices == []


def test_confirmar_eliminar_borra_letra(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-15",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.letras == []


def test_confirmar_eliminar_borra_gasto(run_view, db):
    db.create_expense({"kind": "variable", "name": "Reparación", "category": "Servicios",
                       "branch": "Sucursal 1", "amount": 75.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Sí, eliminar")
    assert not at.exception
    assert db.expenses == []


def _seed_gasto_fijo_con_futuros(db):
    fx = db.create_fixed_expense({"name": "Alquiler", "category": "Alquiler", "branch": "Sucursal 1",
                                  "amount": 1000.0, "pay_day": 15})
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler", "branch": "Sucursal 1",
                       "amount": 1000.0, "due_date": "2020-01-15", "status": "pendiente",
                       "fixed_expense_id": fx["id"], "period": "2020-01"})
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler", "branch": "Sucursal 1",
                       "amount": 1000.0, "due_date": "2020-02-15", "status": "pendiente",
                       "fixed_expense_id": fx["id"], "period": "2020-02"})
    # una ya pagada, de un mes anterior: no debe tocarse
    db.create_expense({"kind": "fijo", "name": "Alquiler", "category": "Alquiler", "branch": "Sucursal 1",
                       "amount": 1000.0, "due_date": "2019-12-15", "status": "pagado",
                       "fixed_expense_id": fx["id"], "period": "2019-12", "paid_at": "2019-12-15"})
    return fx


def test_eliminar_gasto_fijo_ofrece_solo_este_o_futuros(run_view, db):
    _seed_gasto_fijo_con_futuros(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    assert not at.exception
    assert any(b.label == "Solo este" for b in at.button)
    assert any(b.label == "Este y los futuros" for b in at.button)
    assert not any(b.label == "Sí, eliminar" for b in at.button)


def test_eliminar_solo_este_no_toca_futuros_ni_desactiva(run_view, db):
    # Nota: Calendario llama a ensure_expense_instances() al cargar, que
    # genera instancias reales alrededor de la fecha de HOY para cualquier
    # gasto fijo activo — por eso se revisan periodos puntuales en vez del
    # total de db.expenses (que sí va a traer esas de más).
    fx = _seed_gasto_fijo_con_futuros(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Solo este")
    assert not at.exception
    periods = [e["period"] for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert "2020-01" not in periods
    assert "2020-02" in periods
    assert "2019-12" in periods
    assert db.fixed_expenses[0]["active"] is True


def test_eliminar_este_y_futuros_borra_pendientes_y_desactiva_plantilla(run_view, db):
    fx = _seed_gasto_fijo_con_futuros(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "Este y los futuros")
    assert not at.exception
    propias = [e for e in db.expenses if e["fixed_expense_id"] == fx["id"]]
    assert all(e["status"] == "pagado" for e in propias)
    assert any(e["period"] == "2019-12" for e in propias)   # la pagada se mantiene intacta
    assert db.fixed_expenses[0]["id"] == fx["id"] and db.fixed_expenses[0]["active"] is False


def test_eliminar_gasto_variable_sigue_con_un_solo_boton(run_view, db):
    db.create_expense({"kind": "variable", "name": "Reparación", "category": "Servicios",
                       "branch": "Sucursal 1", "amount": 75.0, "due_date": "2020-01-15", "status": "pendiente"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    assert not any(b.label == "Solo este" for b in at.button)
    assert any(b.label == "Sí, eliminar" for b in at.button)


def test_cancelar_eliminar_no_borra_y_vuelve_al_dia(run_view, db):
    _seed_invoice(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-15")
    click(at, "Eliminar")
    click(at, "No, cancelar")
    assert not at.exception
    assert db.invoices
    assert at.session_state["_cal_day"] == "2020-01-15"
