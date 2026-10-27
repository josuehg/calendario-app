"""Toggle 'Mostrar pagados' en Calendario: superpone el historial de lo ya
pagado en el grid/lista y en el diálogo del día, sin alterar ningún total
(que sigue siendo siempre sobre lo pendiente)."""
from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _seed_pagada_y_pendiente(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Pagada", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 250.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-10", "status": "pagada",
        "paid_at": "2020-01-10", "paid_by": "Josue",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Pendiente", "invoice_number": "F-2",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })


def test_pagados_no_aparecen_por_defecto(run_view, db):
    _seed_pagada_y_pendiente(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "✅" not in text  # la marca de pagado no aparece sin activar el toggle


def test_activar_toggle_muestra_marca_en_el_dia(run_view, db):
    _seed_pagada_y_pendiente(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    cb = next(c for c in at.checkbox if c.label == "Mostrar pagados")
    at = cb.set_value(True).run()
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "✅" in text and "S/ 250.00" in text


def test_toggle_no_altera_el_total_del_mes(run_view, db):
    _seed_pagada_y_pendiente(db)
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    total_antes = next(m.value for m in at.metric if m.label == "Total del mes")
    cb = next(c for c in at.checkbox if c.label == "Mostrar pagados")
    at = cb.set_value(True).run()
    total_despues = next(m.value for m in at.metric if m.label == "Total del mes")
    assert total_antes == total_despues == "S/ 100.00"  # solo lo pendiente


def test_dia_solo_con_pagado_tambien_se_puede_abrir(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Pagada", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 250.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-10", "status": "pagada",
        "paid_at": "2020-01-10", "paid_by": "Josue",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    cb = next(c for c in at.checkbox if c.label == "Mostrar pagados")
    at = cb.set_value(True).run()
    assert not at.exception
    at = click(at, "👁")
    assert not at.exception
    text = " ".join(str(c.value) for c in at.caption) + " ".join(str(m.value) for m in at.markdown)
    assert "Prov Pagada" in text and "pagó Josue" in text


def test_dia_dialogo_muestra_seccion_de_pagados(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Pagada", "invoice_number": "F-2",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 250.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pagada",
        "paid_at": "2020-01-15", "paid_by": "Josue",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, cal_f_pagados=True, _cal_day="2020-01-15")
    assert not at.exception
    text = " ".join(str(c.value) for c in at.caption) + " ".join(str(m.value) for m in at.markdown)
    assert "Ya pagados ese día" in text
    assert "Prov Pagada" in text
