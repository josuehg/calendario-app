"""Saldo de caja / disponible para comprometer, mostrado al tope de Presupuesto."""

VIEW = "views/5_Presupuesto.py"


def test_sin_saldo_inicial_configurado_muestra_aviso(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("Configura el saldo inicial" in str(i.value) for i in at.info)
    assert not any(m.label == "💰 Disponible para comprometer" for m in at.metric)


def test_con_saldo_inicial_muestra_metricas(run_view, db):
    db.settings["caja_saldo_inicial"] = 1000.0
    db.settings["caja_saldo_inicial_fecha"] = "2026-09-01"
    db.create_income({"branch": "Sucursal 1", "date": "2026-09-05", "amount": 500.0})
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 300.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-20", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Saldo de caja actual"] == "S/ 1,500.00"
    assert metrics["Comprometido (pendiente)"] == "S/ 300.00"
    assert metrics["💰 Disponible para comprometer"] == "S/ 1,200.00"


def test_disponible_negativo_muestra_error(run_view, db):
    db.settings["caja_saldo_inicial"] = 100.0
    db.settings["caja_saldo_inicial_fecha"] = "2026-09-01"
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 5000.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-20", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("más comprometido" in str(e.value) for e in at.error)
