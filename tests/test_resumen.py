"""Filtro por tipo (Contado/Crédito/Letras) en Resumen, para ubicar rápido
las facturas al contado pendientes de marcar 'Pagado'."""
from tests.conftest import widget


VIEW = "views/0_Resumen.py"


def _set_filtro(at, valor):
    for r in at.radio:
        if r.key == "resumen_filtro_tipo":
            return r.set_value(valor).run()
    raise AssertionError("no se encontró el radio de filtro (resumen_filtro_tipo)")


def _seed(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Contado Uno", "invoice_number": "C-1",
        "document_type": "Nota de compra", "doc_type": "contado", "amount": 50.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Credito Uno", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 200.0,
        "issue_date": "2026-09-01", "due_date": "2026-10-01", "status": "pendiente",
    })
    db.invoices.append({"id": "i-canje", "vendor": "Prov Canje", "invoice_number": "FC-1",
                        "branch": "Sucursal 1", "doc_type": "credito", "amount": 500.0,
                        "due_date": "2026-09-01", "issue_date": "2026-08-01", "status": "canjeada"})
    db.create_canje(["i-canje"], [{"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2026-11-01"}],
                    created_by="Administrador")


def test_sin_filtro_muestra_todo(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Contado Uno" in text and "Credito Uno" in text and "Letra L-1" in text


def test_filtro_contado_solo_muestra_facturas_al_contado(run_view, db):
    _seed(db)
    at = _set_filtro(run_view(VIEW, role="admin"), "Contado")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Contado Uno" in text
    assert "Credito Uno" not in text and "Letra L-1" not in text


def test_filtro_credito_excluye_contado_y_letras(run_view, db):
    _seed(db)
    at = _set_filtro(run_view(VIEW, role="admin"), "Crédito")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Credito Uno" in text
    assert "Contado Uno" not in text and "Letra L-1" not in text


def test_filtro_letras_solo_muestra_letras(run_view, db):
    _seed(db)
    at = _set_filtro(run_view(VIEW, role="admin"), "Letras")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Letra L-1" in text
    assert "Contado Uno" not in text and "Credito Uno" not in text


def test_filtro_sin_coincidencias_muestra_aviso(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Contado Uno", "invoice_number": "C-1",
        "document_type": "Nota de compra", "doc_type": "contado", "amount": 50.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    at = _set_filtro(run_view(VIEW, role="admin"), "Letras")
    caps = " ".join(str(c.value) for c in at.caption)
    assert "No hay ninguno con este filtro" in caps
