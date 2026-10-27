"""Guardarraíl de 'cuánto me alcanza según mi proyección de caja' al armar
un canje de facturas a letras, usando el vencimiento de la letra más próxima
como plazo implícito."""
from datetime import date, timedelta

VIEW = "views/3_Canjear_a_Letras.py"

_VENCIMIENTO = date.today() + timedelta(days=30)
_SALDO_FECHA = (date.today() - timedelta(days=60)).isoformat()


def _seleccionar_factura(at, label_contains):
    for ms in at.multiselect:
        opts = [o for o in ms.options if label_contains in o]
        if opts:
            return ms.select(opts[0]).run()
    raise AssertionError(f"no se encontró una factura con {label_contains!r}")


def _fijar_fecha_letra(at):
    for di in at.date_input:
        if di.key and di.key.startswith("fecha_"):
            return di.set_value(_VENCIMIENTO).run()
    raise AssertionError("no se encontró el date_input de vencimiento de la letra")


def test_sin_saldo_inicial_no_muestra_nada(run_view, db):
    db.invoices.append({
        "id": "i1", "vendor": "Prov A", "invoice_number": "F-1", "branch": "Sucursal 1",
        "doc_type": "credito", "amount": 400.0, "due_date": _VENCIMIENTO.isoformat(),
        "issue_date": date.today().isoformat(), "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    at = _seleccionar_factura(at, "Prov A")
    at = _fijar_fecha_letra(at)
    assert not at.exception
    assert not any("proyección de caja" in str(w.value) for w in at.warning)
    assert not any("proyección de caja" in str(c.value) for c in at.caption)


def test_canje_que_supera_la_proyeccion_muestra_warning(run_view, db):
    db.settings["caja_saldo_inicial"] = 100.0
    db.settings["caja_saldo_inicial_fecha"] = _SALDO_FECHA
    db.invoices.append({
        "id": "i1", "vendor": "Prov A", "invoice_number": "F-1", "branch": "Sucursal 1",
        "doc_type": "credito", "amount": 999999.0, "due_date": _VENCIMIENTO.isoformat(),
        "issue_date": date.today().isoformat(), "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    at = _seleccionar_factura(at, "Prov A")
    at = _fijar_fecha_letra(at)
    assert not at.exception
    assert any("alcanzaría hasta" in str(w.value) for w in at.warning)


def test_canje_dentro_de_la_proyeccion_muestra_check(run_view, db):
    db.settings["caja_saldo_inicial"] = 1_000_000.0
    db.settings["caja_saldo_inicial_fecha"] = _SALDO_FECHA
    db.invoices.append({
        "id": "i1", "vendor": "Prov A", "invoice_number": "F-1", "branch": "Sucursal 1",
        "doc_type": "credito", "amount": 100.0, "due_date": _VENCIMIENTO.isoformat(),
        "issue_date": date.today().isoformat(), "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    at = _seleccionar_factura(at, "Prov A")
    at = _fijar_fecha_letra(at)
    assert not at.exception
    assert any("te alcanza para este canje" in str(c.value) for c in at.caption)
