"""Módulo de Deudas: capital, tasa y saldo pendiente, separado de la cuota
mensual que ya se registra en Gastos Fijos."""
from datetime import date

from tests.conftest import click, widget

VIEW = "views/9_Deudas.py"


def test_db_create_list_update_delete_debt(db):
    d = db.create_debt({
        "creditor": "Sra Carmen", "debt_type": "informal",
        "principal": 94000.0, "balance": 94000.0, "rate_pct": 10.0, "rate_period": "mensual",
        "monthly_payment": 9400.0,
    })
    assert d["creditor"] == "Sra Carmen"
    assert db.list_debts()[0]["balance"] == 94000.0

    db.update_debt(d["id"], {"balance": 80000.0})
    assert db.list_debts()[0]["balance"] == 80000.0

    db.delete_debt(d["id"])
    assert db.list_debts() == []


def test_list_debts_active_only(db):
    db.create_debt({"creditor": "Activa", "debt_type": "bancario", "principal": 1000.0, "balance": 1000.0})
    db.create_debt({"creditor": "Inactiva", "debt_type": "bancario", "principal": 1000.0,
                    "balance": 0.0, "active": False})
    assert len(db.list_debts()) == 2
    assert len(db.list_debts(active_only=True)) == 1


def test_view_shows_totals_by_type(run_view, db):
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal",
                    "principal": 94000.0, "balance": 94000.0, "rate_pct": 10.0, "rate_period": "mensual"})
    db.create_debt({"creditor": "Scotiabank", "debt_type": "bancario",
                    "principal": 300000.0, "balance": 250000.0, "monthly_payment": 15866.13})
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Saldo total pendiente") == "S/ 344,000.00"
    assert metrics.get("Bancario / formal") == "S/ 250,000.00"
    assert metrics.get("Informal") == "S/ 94,000.00"


def test_empty_state(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Aún no has registrado deudas" in c.value for c in at.caption)


def test_create_debt_via_dialog(run_view, db):
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    widget(at, "dd_creditor").set_value("Sra Marlene").run()
    for r in at.radio:
        if r.key == "dd_type":
            r.set_value("informal").run()
            break
    widget(at, "dd_principal", "number_input").set_value(50000.0).run()
    widget(at, "dd_balance", "number_input").set_value(50000.0).run()
    widget(at, "dd_rate", "number_input").set_value(10.0).run()
    click(at, "Guardar")
    assert not at.exception
    assert db.debts[0]["creditor"] == "Sra Marlene"
    assert db.debts[0]["debt_type"] == "informal"
    assert db.debts[0]["rate_pct"] == 10.0
    assert db.debts[0]["rate_period"] == "mensual"


def test_create_debt_requires_creditor_and_principal(run_view, db):
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    click(at, "Guardar")
    assert any("capital" in e.value.lower() for e in at.error)
    assert not db.debts


def test_edit_debt_prefills_and_saves(run_view, db):
    db.create_debt({"creditor": "Scotiabank", "debt_type": "bancario",
                    "principal": 300000.0, "balance": 300000.0, "monthly_payment": 15866.13})
    at = run_view(VIEW, role="admin")
    click(at, "Editar")
    assert widget(at, "dd_creditor").value == "Scotiabank"
    assert widget(at, "dd_balance", "number_input").value == 300000.0
    widget(at, "dd_balance", "number_input").set_value(290000.0).run()
    click(at, "Guardar")
    assert not at.exception
    assert db.debts[0]["balance"] == 290000.0


def test_delete_debt_requires_confirmation(run_view, db):
    db.create_debt({"creditor": "Por Borrar", "debt_type": "bancario", "principal": 500.0, "balance": 500.0})
    at = run_view(VIEW, role="admin")
    click(at, "Editar")
    click(at, "🗑️ Eliminar esta deuda")
    warns = " ".join(str(w.value) for w in at.warning)
    assert "no se puede deshacer" in warns
    assert db.debts
    click(at, "Sí, eliminar")
    assert not at.exception
    assert not db.debts


def test_search_filters_by_creditor(run_view, db):
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "principal": 94000.0, "balance": 94000.0})
    db.create_debt({"creditor": "Scotiabank", "debt_type": "bancario", "principal": 300000.0, "balance": 300000.0})
    at = run_view(VIEW, role="admin")
    for ti in at.text_input:
        if ti.label == "Buscar acreedor":
            ti.set_value("Carmen").run()
            break
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Carmen" in text and "Scotiabank" not in text


# ---------- vinculación con Gastos Fijos ----------

def _fx_link_selectbox(at):
    for sb in at.selectbox:
        if sb.key == "dd_fx_link":
            return sb
    raise AssertionError("no se encontró el selectbox dd_fx_link")


def test_selectbox_solo_ofrece_categorias_de_prestamo(run_view, db):
    db.create_fixed_expense({"name": "Scotiabank", "category": "Préstamos Pers. Jur.",
                             "branch": None, "amount": 15866.13, "pay_day": 5})
    db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                             "branch": None, "amount": 9400.0, "pay_day": 18})
    db.create_fixed_expense({"name": "Alquiler Colón", "category": "Alquiler",
                             "branch": "COLON", "amount": 3000.0, "pay_day": 1})
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    sb = _fx_link_selectbox(at)
    assert any("Scotiabank" in o for o in sb.options)
    assert any("Sra Carmen" in o for o in sb.options)
    assert not any("Alquiler" in o for o in sb.options)


def test_vincular_prestamo_precarga_acreedor_y_tipo(run_view, db):
    db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                             "branch": None, "amount": 9400.0, "pay_day": 18})
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    sb = _fx_link_selectbox(at)
    opcion = next(o for o in sb.options if "Sra Carmen" in o)
    sb.set_value(opcion).run()
    assert any("Sra Carmen" in ti.value for ti in at.text_input if ti.key == "dd_creditor_linked")
    radio = next(r for r in at.radio if r.key == "dd_type")
    assert radio.value == "informal"


def test_guardar_vinculado_guarda_fixed_expense_id_y_cuota(run_view, db):
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                                  "branch": None, "amount": 9400.0, "pay_day": 18})
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    sb = _fx_link_selectbox(at)
    sb.set_value(next(o for o in sb.options if "Sra Carmen" in o)).run()
    widget(at, "dd_principal", "number_input").set_value(94000.0).run()
    widget(at, "dd_balance", "number_input").set_value(94000.0).run()
    click(at, "Guardar")
    assert not at.exception
    assert db.debts[0]["fixed_expense_id"] == fx["id"]
    assert db.debts[0]["creditor"] == "Sra Carmen"
    assert db.debts[0]["monthly_payment"] == 9400.0


def test_prestamo_ya_vinculado_no_se_ofrece_de_nuevo(run_view, db):
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                                  "branch": None, "amount": 9400.0, "pay_day": 18})
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "fixed_expense_id": fx["id"],
                    "principal": 94000.0, "balance": 94000.0, "monthly_payment": 9400.0})
    at = run_view(VIEW, role="admin")
    click(at, "➕ Nueva deuda")
    sb = _fx_link_selectbox(at)
    assert not any("Sra Carmen" in o for o in sb.options)


def test_editar_deuda_vinculada_preselecciona_su_propio_prestamo(run_view, db):
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                                  "branch": None, "amount": 9400.0, "pay_day": 18})
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "fixed_expense_id": fx["id"],
                    "principal": 94000.0, "balance": 94000.0, "monthly_payment": 9400.0})
    at = run_view(VIEW, role="admin")
    click(at, "Editar")
    sb = _fx_link_selectbox(at)
    assert "Sra Carmen" in sb.value


def test_listado_muestra_cuota_en_vivo_del_gasto_fijo(run_view, db):
    """Si se actualiza la cuota en Gastos Fijos, Deudas debe reflejarla sola,
    sin tener que re-editar la deuda."""
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                                  "branch": None, "amount": 9400.0, "pay_day": 18})
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "fixed_expense_id": fx["id"],
                    "principal": 94000.0, "balance": 94000.0, "monthly_payment": 9400.0})
    db.update_fixed_expense(fx["id"], {"name": "Sra Carmen", "category": "Préstamos Usu", "branch": None,
                                       "amount": 11000.0, "pay_day": 18, "active": True,
                                       "start_month": None, "end_month": None})
    at = run_view(VIEW, role="admin")
    text = " ".join(str(c.value) for c in at.caption)
    assert "S/ 11,000.00" in text
    assert "S/ 9,400.00" not in text


def test_listado_marca_vinculada(run_view, db):
    fx = db.create_fixed_expense({"name": "Sra Carmen", "category": "Préstamos Usu",
                                  "branch": None, "amount": 9400.0, "pay_day": 18})
    db.create_debt({"creditor": "Sra Carmen", "debt_type": "informal", "fixed_expense_id": fx["id"],
                    "principal": 94000.0, "balance": 94000.0, "monthly_payment": 9400.0})
    db.create_debt({"creditor": "Deuda Suelta", "debt_type": "bancario",
                    "principal": 1000.0, "balance": 1000.0})
    at = run_view(VIEW, role="admin")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🔗 vinculada a Gastos Fijos" in text
