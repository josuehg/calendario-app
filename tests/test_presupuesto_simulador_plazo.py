"""Simulador "¿cuánto puedo comprometer con un proveedor nuevo?" en
Presupuesto — proyecta la caja a la fecha en que vencería la compra, según
el plazo del proveedor (30/45/60/75/90 días)."""

VIEW = "views/5_Presupuesto.py"


def _config_saldo(db, monto=1000.0, fecha="2026-09-01"):
    db.settings["caja_saldo_inicial"] = monto
    db.settings["caja_saldo_inicial_fecha"] = fecha


def test_sin_saldo_inicial_no_muestra_simulador(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert not any(m.label.startswith("Máximo recomendado") for m in at.metric)


def test_simulador_resta_lo_comprometido_antes_del_vencimiento(run_view, db):
    _config_saldo(db, monto=1000.0, fecha="2026-09-01")
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Urgente", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 400.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-20", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    for r in at.radio:
        if r.key == "pp_sim_plazo":
            at = r.set_value(60).run()
            break
    assert not at.exception
    metric = next(m for m in at.metric if m.label.startswith("Máximo recomendado a 60 días"))
    # Saldo 1000 - 400 ya comprometido antes del vencimiento a 60 días, sin venta (sin ingresos).
    assert metric.value == "S/ 600.00"


def test_simulador_en_rojo_muestra_error(run_view, db):
    _config_saldo(db, monto=100.0, fecha="2026-09-01")
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Grande", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 5000.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-20", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert any("proyectas caja en rojo" in str(e.value) for e in at.error)
