"""Guardarraíl de 'cuánto me alcanza según mi proyección de caja' al
registrar una factura a crédito, usando el plazo del proveedor."""
from datetime import date

from tests.conftest import widget

VIEW = "views/1_Nueva_Factura.py"


def _seed_vendor_credito(db, term_days=60):
    db.vendors.append({
        "id": 1, "name": "Prov Credito", "ruc": "20999999999",
        "doc_type": "credito", "term_days": term_days,
    })


def test_sin_saldo_inicial_no_muestra_nada(run_view, db):
    _seed_vendor_credito(db)
    at = run_view(VIEW, role="admin")
    widget(at, "nf_query").set_value("20999999999").run()
    widget(at, "nf_amount", "number_input").set_value(1000.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    assert not at.exception
    assert not any("proyección de caja" in str(w.value) for w in at.warning)
    assert not any("proyección de caja" in str(c.value) for c in at.caption)


def test_monto_que_supera_la_proyeccion_muestra_warning(run_view, db):
    db.settings["caja_saldo_inicial"] = 100.0
    db.settings["caja_saldo_inicial_fecha"] = "2026-01-01"
    _seed_vendor_credito(db, term_days=60)
    at = run_view(VIEW, role="admin")
    widget(at, "nf_query").set_value("20999999999").run()
    widget(at, "nf_amount", "number_input").set_value(999999.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    assert not at.exception
    assert any("alcanzaría hasta" in str(w.value) for w in at.warning)


def test_monto_dentro_de_la_proyeccion_muestra_check(run_view, db):
    db.settings["caja_saldo_inicial"] = 1_000_000.0
    db.settings["caja_saldo_inicial_fecha"] = "2026-01-01"
    _seed_vendor_credito(db, term_days=60)
    at = run_view(VIEW, role="admin")
    widget(at, "nf_query").set_value("20999999999").run()
    widget(at, "nf_amount", "number_input").set_value(10.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    assert not at.exception
    assert any("te alcanza para este monto" in str(c.value) for c in at.caption)


def test_sucursal_no_ve_la_proyeccion(run_view, db):
    db.settings["caja_saldo_inicial"] = 100.0
    db.settings["caja_saldo_inicial_fecha"] = "2026-01-01"
    _seed_vendor_credito(db, term_days=60)
    at = run_view(VIEW, role="branch", branch="Sucursal 1")
    widget(at, "nf_query").set_value("20999999999").run()
    widget(at, "nf_amount", "number_input").set_value(999999.0).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    assert not at.exception
    assert not any("proyección de caja" in str(w.value) for w in at.warning)
