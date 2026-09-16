"""Subcategorías de gasto (dentro de una categoría)."""
from datetime import date

import pytest

from tests.conftest import click, widget


# ---------- db ----------

def test_add_and_list_subcategories_scoped_to_category(db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Servicios", "Agua")
    db.add_expense_subcategory("Alquiler", "Local A")
    assert {s["name"] for s in db.list_expense_subcategories("Servicios")} == {"Luz", "Agua"}
    assert {s["name"] for s in db.list_expense_subcategories("Alquiler")} == {"Local A"}
    assert len(db.list_expense_subcategories()) == 3


def test_rename_subcategory_cascades(db):
    db.add_expense_subcategory("Servicios", "Luz")
    sid = db.list_expense_subcategories("Servicios")[0]["id"]
    fx = db.create_fixed_expense({"name": "Luz local", "category": "Servicios", "subcategory": "Luz",
                                  "branch": None, "amount": 100.0, "pay_day": 5})
    db.ensure_expense_instances()
    db.rename_expense_subcategory(sid, "Electricidad")
    assert db.list_expense_subcategories("Servicios")[0]["name"] == "Electricidad"
    assert db.fixed_expenses[0]["subcategory"] == "Electricidad"
    assert all(e["subcategory"] == "Electricidad" for e in db.expenses if e["fixed_expense_id"] == fx["id"])


def test_delete_subcategory(db):
    db.add_expense_subcategory("Servicios", "Luz")
    sid = db.list_expense_subcategories("Servicios")[0]["id"]
    db.delete_expense_subcategory(sid)
    assert db.list_expense_subcategories("Servicios") == []


def test_rename_category_cascades_to_its_subcategories(db):
    db.add_expense_subcategory("Servicios", "Luz")
    cat_id = next(c["id"] for c in db.expense_categories if c["name"] == "Servicios")
    db.rename_expense_category(cat_id, "Servicios básicos")
    assert db.expense_subcategories[0]["category"] == "Servicios básicos"


def test_delete_category_removes_its_subcategories(db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Alquiler", "Local A")
    cat_id = next(c["id"] for c in db.expense_categories if c["name"] == "Servicios")
    db.delete_expense_category(cat_id)
    names = {s["category"] for s in db.expense_subcategories}
    assert "Servicios" not in names
    assert "Alquiler" in names


# ---------- Configuración ----------

def test_configuracion_shows_subcategorias_section(run_view, db):
    at = run_view("views/6_Configuracion.py", role="admin")
    assert not at.exception
    assert any("Subcategorías de gasto" in str(m.value) for m in at.subheader)


def test_add_subcategory_via_configuracion(run_view, db):
    at = run_view("views/6_Configuracion.py", role="admin")
    for sb in at.selectbox:
        if sb.key == "sc_cat_pick":
            sb.set_value("Servicios").run()
            break
    for ti in at.text_input:
        if ti.label == "Nueva subcategoría":
            ti.set_value("Internet").run()
            break
    for b in at.button:
        if b.key == "subcat_add_submit":
            b.click().run()
            break
    assert not at.exception
    assert any(s["name"] == "Internet" and s["category"] == "Servicios" for s in db.expense_subcategories)
    assert not any(c["name"] == "Internet" for c in db.expense_categories)


# ---------- Gastos: nuevo gasto fijo ----------

def test_new_fixed_expense_dialog_filters_subcategories_by_category(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Alquiler", "Local A")
    at = run_view("views/7_Gastos.py", role="admin")
    click(at, "➕ Nuevo gasto fijo")
    # por defecto la categoría es la primera de la lista (Alquiler): debe
    # ofrecer "Local A", no "Luz"
    subcat_widget = next(sb for sb in at.selectbox if sb.key == "fx_subcat")
    assert "Local A" in subcat_widget.options
    assert "Luz" not in subcat_widget.options


def test_create_fixed_expense_with_subcategory(run_view, db):
    db.add_expense_subcategory("Servicios", "Internet")
    at = run_view("views/7_Gastos.py", role="admin")
    click(at, "➕ Nuevo gasto fijo")
    for ti in at.text_input:
        if ti.key == "fx_name":
            ti.set_value("Plan de internet").run()
            break
    for sb in at.selectbox:
        if sb.key == "fx_cat":
            sb.set_value("Servicios").run()
            break
    for sb in at.selectbox:
        if sb.key == "fx_subcat":
            sb.set_value("Internet").run()
            break
    for ni in at.number_input:
        if ni.key == "fx_amount":
            ni.set_value(150.0).run()
            break
    click(at, "Guardar")
    assert not at.exception
    fx = next(f for f in db.fixed_expenses if f["name"] == "Plan de internet")
    assert fx["subcategory"] == "Internet"


def test_switching_category_resets_subcategory_without_crash(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Alquiler", "Local A")
    fx = db.create_fixed_expense({"name": "Luz tienda", "category": "Servicios", "subcategory": "Luz",
                                  "branch": None, "amount": 80.0, "pay_day": 10})
    at = run_view("views/7_Gastos.py", role="admin")
    for b in at.button:
        if b.key and b.key.startswith("fx_edit_"):
            b.click().run()
            break
    for sb in at.selectbox:
        if sb.key == "fx_cat":
            sb.set_value("Alquiler").run()
            break
    assert not at.exception
    subcat_widget = next(sb for sb in at.selectbox if sb.key == "fx_subcat")
    assert subcat_widget.value == "— Ninguna —"


# ---------- Gastos: gasto variable ----------

def test_variable_expense_category_subcategory_outside_form(run_view, db):
    db.add_expense_subcategory("Servicios", "Software")
    at = run_view("views/7_Gastos.py", role="admin")
    for sb in at.selectbox:
        if sb.key == "gv_cat":
            sb.set_value("Servicios").run()
            break
    for sb in at.selectbox:
        if sb.key == "gv_subcat":
            sb.set_value("Software").run()
            break
    for ti in at.text_input:
        if ti.label == "Descripción":
            ti.set_value("Licencia anual").run()
            break
    for ni in at.number_input:
        if ni.label.startswith("Monto"):
            ni.set_value(200.0).run()
            break
    click(at, "Registrar gasto variable")
    assert not at.exception
    e = next(x for x in db.expenses if x["name"] == "Licencia anual")
    assert e["category"] == "Servicios"
    assert e["subcategory"] == "Software"


def test_row_meta_shows_subcategory(run_view, db):
    db.create_expense({"kind": "variable", "name": "Internet oficina", "category": "Servicios",
                       "subcategory": "Internet", "branch": None, "amount": 100.0,
                       "due_date": date.today().isoformat(), "status": "pendiente"})
    at = run_view("views/7_Gastos.py", role="admin")
    assert not at.exception
    caps = " ".join(str(c.value) for c in at.caption)
    assert "Internet" in caps
