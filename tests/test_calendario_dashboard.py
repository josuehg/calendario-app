"""Dashboard del mes y resumen semanal en Calendario."""
from tests.conftest import click


VIEW = "views/4_Calendario.py"


def test_metrics_total_y_conteo_del_mes_mostrado(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 100.0,
        "issue_date": "2019-12-01", "due_date": "2020-01-05", "status": "pendiente",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov B", "invoice_number": "F-2",
        "document_type": "Factura", "doc_type": "credito", "amount": 50.0,
        "issue_date": "2019-12-20", "due_date": "2020-01-20", "status": "pendiente",
    })
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Otro Mes", "invoice_number": "F-3",
        "document_type": "Factura", "doc_type": "credito", "amount": 500.0,
        "issue_date": "2019-11-01", "due_date": "2020-02-10", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Total del mes"] == "S/ 150.00"
    assert metrics["N° de pagos"] == "2"


def test_metrics_vencido_del_mes_para_mes_completamente_pasado(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Viejo", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 200.0,
        "issue_date": "2019-12-01", "due_date": "2020-01-05", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Vencido del mes"] == "S/ 200.00"
    assert metrics["Por vencer del mes"] == "S/ 0.00"


def test_metrics_por_vencer_del_mes_para_mes_completamente_futuro(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Futuro", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 300.0,
        "issue_date": "2029-12-01", "due_date": "2030-01-20", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2030, cal_month=1)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Por vencer del mes"] == "S/ 300.00"
    assert metrics["Vencido del mes"] == "S/ 0.00"


def test_boton_ver_es_compacto_icono(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-05", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    assert any(b.label == "👁" for b in at.button)
    assert not any(b.label == "Ver" for b in at.button)


def test_resumen_semanal_muestra_filas_con_totales(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 120.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-05", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    assert any("Resumen semanal" in str(s.value) for s in at.subheader)
    text = " ".join(str(m.value) for m in at.markdown)
    assert "S/ 120.00" in text


def test_dia_sin_pagos_no_tiene_boton(run_view, db):
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    assert not any(b.label == "👁" for b in at.button)
