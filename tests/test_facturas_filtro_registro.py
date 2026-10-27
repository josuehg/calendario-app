"""Filtro 'Registró' en Facturas — para encontrar rápido las facturas que
uno mismo registró (ej. en nombre de una sucursal que no las registró),
y revisarlas/validarlas después sin mezclarlas con las demás."""

VIEW = "views/2_Consolidado.py"


def _seed(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
        "registered_by": "JOSUE HUERTAS",
    })
    db.create_invoice({
        "branch": "Sucursal 2", "vendor": "Prov B", "invoice_number": "F-2",
        "document_type": "Factura", "doc_type": "contado", "amount": 200.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
        "registered_by": "RUTH PARI",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov C", "invoice_number": "F-3",
        "document_type": "Factura", "doc_type": "contado", "amount": 300.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })  # sin registered_by


def test_filtro_registro_lista_opciones_de_quienes_registraron(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    sb = next(sb for sb in at.selectbox if sb.label == "Registró")
    assert sb.options == ["Todos", "JOSUE HUERTAS", "RUTH PARI"]


def test_filtrar_por_registro_muestra_solo_esas_facturas(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    sb = next(sb for sb in at.selectbox if sb.label == "Registró")
    at = sb.set_value("JOSUE HUERTAS").run()
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown) + " ".join(str(c.value) for c in at.caption)
    assert "Prov A" in text
    assert "Prov B" not in text and "Prov C" not in text


def test_filtro_todos_muestra_todas(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    sb = next(sb for sb in at.selectbox if sb.label == "Registró")
    at = sb.set_value("Todos").run()
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Prov A" in text and "Prov B" in text and "Prov C" in text
