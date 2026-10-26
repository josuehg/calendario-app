"""Toggle 'Mes / Lista' en Calendario: una vista de agenda (un renglón por
día con pagos) además del grid mensual, más cómoda en celular o cuando hay
mucho que revisar en un mes."""
from tests.conftest import click

VIEW = "views/4_Calendario.py"


def _goto_lista(at):
    for r in at.radio:
        if r.key == "cal_vista":
            return r.set_value("📋 Lista").run()
    raise AssertionError("no se encontró el radio cal_vista")


def test_vista_por_defecto_es_mes(run_view, db):
    at = run_view(VIEW, role="admin")
    r = next(r for r in at.radio if r.key == "cal_vista")
    assert r.value == "📅 Mes"


def test_lista_muestra_un_renglon_por_dia_con_pagos(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    at = _goto_lista(at)
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "15 de enero" in text
    assert any(b.label == "Ver" for b in at.button)


def test_click_ver_en_lista_abre_el_dialogo_del_dia(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    at = _goto_lista(at)
    click(at, "Ver")
    assert not at.exception
    assert at.session_state["_cal_day"] == "2020-01-15"
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Prov A" in text


def test_lista_vacia_muestra_aviso(run_view, db):
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    at = _goto_lista(at)
    assert not at.exception
    caps = " ".join(str(c.value) for c in at.caption)
    assert "No hay pagos este mes con estos filtros" in caps


def test_lista_respeta_filtro_de_tipo(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Credito", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-15", "status": "pendiente",
    })
    db.create_letra({"numero": "L-1", "monto": 200.0, "fecha_vencimiento": "2020-01-20",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    for sb in at.selectbox:
        if sb.key == "cal_f_tipo":
            sb.set_value("Letras").run()
            break
    at = _goto_lista(at)
    text = " ".join(str(m.value) for m in at.markdown)
    assert "20 de enero" in text
    assert "15 de enero" not in text
