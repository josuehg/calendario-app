"""Backup completo de datos (Configuración): un solo Excel con una pestaña
por tabla, para analisis externo sin tener que exportar tabla por tabla
desde Supabase."""
import io

import pandas as pd

VIEW = "views/6_Configuracion.py"


def test_backup_button_renders_with_empty_db(run_view, db):
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("backup completo" in b.label.lower() for b in at.download_button)


def test_dict_list_to_xlsx_bytes_writes_one_sheet_per_table(db):
    import utils

    raw = utils.dict_list_to_xlsx_bytes({
        "invoices": [{"vendor": "Prov A", "amount": 100.0}],
        "vendors": [{"name": "Prov A"}],
        "empty_table": [],
    })
    assert isinstance(raw, bytes) and len(raw) > 0
    xls = pd.ExcelFile(io.BytesIO(raw))
    assert set(xls.sheet_names) == {"invoices", "vendors", "empty_table"}
    inv = pd.read_excel(xls, sheet_name="invoices")
    assert inv["vendor"].tolist() == ["Prov A"]


def test_backup_includes_real_data(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Backup", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "contado", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin")
    assert not at.exception
    assert any("backup completo" in b.label.lower() for b in at.download_button)
