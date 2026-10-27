"""Estado de Egresos: compras a proveedores + gastos por categoría del mes,
por vencimiento/emisión."""

VIEW = "views/11_Estado_Egresos.py"


def test_muestra_compras_y_gastos_del_mes_actual(run_view, db):
    import datetime
    hoy = datetime.date.today()
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 1000.0,
        "issue_date": hoy.replace(day=1).isoformat(), "due_date": hoy.replace(day=25).isoformat(),
        "status": "pendiente",
    })
    db.expenses.append({
        "id": "e1", "kind": "fijo", "fixed_expense_id": None, "period": None,
        "name": "Alquiler local", "category": "Alquiler", "subcategory": None, "branch": None,
        "amount": 3000.0, "due_date": hoy.replace(day=5).isoformat(), "status": "pendiente",
        "notes": None,
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Total del mes"] == "S/ 1,000.00"
    text = " ".join(str(m.value) for m in at.markdown)
    assert "TOTAL EGRESOS DEL MES" in text
    assert "S/ 4,000.00" in text  # 1000 compras + 3000 alquiler


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _titulo_mes(at):
    return next(m.value for m in at.markdown if any(mes in str(m.value).lower() for mes in MESES))


def test_navegar_a_mes_anterior_cambia_el_periodo(run_view, db):
    at = run_view(VIEW, role="admin")
    titulo_antes = _titulo_mes(at)
    for b in at.button:
        if "anterior" in b.label.lower():
            at = b.click().run()
            break
    else:
        raise AssertionError("no se encontró el botón de mes anterior")
    assert not at.exception
    assert _titulo_mes(at) != titulo_antes


def test_sin_gastos_en_el_mes_muestra_aviso(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("No hay gastos operativos" in str(c.value) for c in at.caption)
