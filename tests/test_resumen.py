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


def test_vencido_muestra_la_fecha_tambien(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Vencido Uno", "invoice_number": "V-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2019-12-01", "due_date": "2020-01-01", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🔴 Vencido" in text
    assert "01/01/20" in text


def test_sin_filtro_muestra_todo(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Contado Uno" in text and "Credito Uno" in text and "Letra L-1" in text


def test_mas_de_veinte_letras_no_se_pierden_en_silencio(run_view, db):
    """Regresión: el tope de 15 por sección cortaba las letras más lejanas
    (ej. las de diciembre) sin avisar — ahora debe salir un '+N más'."""
    for i in range(22):
        db.create_letra({
            "numero": f"L-{i}", "monto": 100.0, "fecha_vencimiento": f"2026-{10 + i % 3:02d}-05",
            "vendor": f"Prov {i}", "branch": "Sucursal 1",
        })
    at = _set_filtro(run_view(VIEW, role="admin"), "Letras")
    caps = " ".join(str(c.value) for c in at.caption)
    assert "+ 2 más" in caps
    assert "Letras → Todas las letras" in caps


def test_todos_agrupa_por_tipo_con_encabezados_y_subtotal(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="admin")
    text = " ".join(str(m.value) for m in at.markdown)
    assert "📄 Facturas a crédito" in text and "S/ 200.00" in text
    assert "💵 Contado" in text and "S/ 50.00" in text
    assert "🔁 Letras" in text and "S/ 500.00" in text
    # y los encabezados de grupo deben aparecer antes que las filas de otro
    # grupo (no deben seguir mezclados en una sola lista por fecha)
    idx_credito = text.index("📄 Facturas a crédito")
    idx_contado = text.index("💵 Contado")
    idx_letras = text.index("🔁 Letras")
    assert idx_credito < idx_contado < idx_letras


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
