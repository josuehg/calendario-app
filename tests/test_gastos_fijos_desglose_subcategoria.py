"""Desglose por subcategoría dentro de cada categoría, en Gastos fijos."""
from tests.conftest import click, widget

VIEW = "views/7_Gastos.py"
FIJOS = "🔁 Gastos fijos"


def _goto(at, section):
    for r in at.radio:
        if r.key == "gx_section":
            return r.set_value(section).run()
    raise AssertionError("no se encontró el radio de sección (gx_section)")


def test_shows_subcategory_subheaders_when_used(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Servicios", "Internet")
    db.create_fixed_expense({"name": "Luz A", "category": "Servicios", "subcategory": "Luz",
                             "branch": "Sucursal 1", "amount": 300.0, "pay_day": 18})
    db.create_fixed_expense({"name": "Luz B", "category": "Servicios", "subcategory": "Luz",
                             "branch": "Sucursal 2", "amount": 280.0, "pay_day": 18})
    db.create_fixed_expense({"name": "Internet oficina", "category": "Servicios", "subcategory": "Internet",
                             "branch": None, "amount": 150.0, "pay_day": 20})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    assert not at.exception
    md = [str(m.value) for m in at.markdown]
    assert any("Luz" in x and "%" in x for x in md)
    assert any("Internet" in x and "%" in x for x in md)


def test_items_without_subcategory_land_in_sin_subcategoria_bucket(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.create_fixed_expense({"name": "Luz A", "category": "Servicios", "subcategory": "Luz",
                             "branch": None, "amount": 300.0, "pay_day": 18})
    db.create_fixed_expense({"name": "Software", "category": "Servicios", "subcategory": None,
                             "branch": None, "amount": 90.0, "pay_day": 5})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    md = [str(m.value) for m in at.markdown]
    assert any("Sin subcategoría" in x for x in md)


def test_category_without_any_subcategory_has_no_breakdown(run_view, db):
    db.create_fixed_expense({"name": "Alquiler A", "category": "Alquiler", "subcategory": None,
                             "branch": "Sucursal 1", "amount": 1000.0, "pay_day": 5})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    md = [str(m.value) for m in at.markdown]
    assert not any("Sin subcategoría" in x for x in md)
    assert any(x == "**Alquiler A**" for x in md)


def test_subcategory_breakdown_only_applies_when_grouping_by_categoria(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.create_fixed_expense({"name": "Luz A", "category": "Servicios", "subcategory": "Luz",
                             "branch": "Sucursal 1", "amount": 300.0, "pay_day": 18})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    for r in at.radio:
        if r.key == "fx_group_by":
            r.set_value("Sucursal").run()
            break
    assert not at.exception
    md = [str(m.value) for m in at.markdown]
    assert not any("↳" in x for x in md)


def test_subtotals_of_subgroups_add_up_to_category_subtotal(run_view, db):
    db.add_expense_subcategory("Servicios", "Luz")
    db.add_expense_subcategory("Servicios", "Internet")
    db.create_fixed_expense({"name": "Luz A", "category": "Servicios", "subcategory": "Luz",
                             "branch": None, "amount": 300.0, "pay_day": 18})
    db.create_fixed_expense({"name": "Internet", "category": "Servicios", "subcategory": "Internet",
                             "branch": None, "amount": 150.0, "pay_day": 20})
    at = _goto(run_view(VIEW, role="admin"), FIJOS)
    md = [str(m.value) for m in at.markdown]
    cat_line = next(x for x in md if x.startswith("**S/") and "del total activo" in x)
    assert "S/ 450.00" in cat_line
    assert any("S/ 300.00" in x and "Luz" in x for x in md)
    assert any("S/ 150.00" in x and "Internet" in x for x in md)
