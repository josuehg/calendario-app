"""#5 montos exactos (Decimal) y #6 renombrar proveedor en cascada."""
import pytest

from tests.conftest import click, widget


@pytest.fixture
def utils(db):
    import utils as u
    return u


# ---------- #5: montos ----------

def test_round2_half_up(utils):
    assert utils.round2(1.005) == 1.01
    assert utils.round2(2.675) == 2.68
    assert utils.round2(None) == 0.0
    assert utils.round2("3.1") == 3.1


def test_dsum_no_binary_drift(utils):
    # 0.1 + 0.2 + 0.3 en float da 0.6000000000000001
    assert utils.dsum([0.1, 0.2, 0.3]) == 0.6
    assert utils.dsum([1712.50, 3000.00, 84.99]) == 4797.49
    assert utils.dsum([]) == 0.0


def test_money_uses_round2(utils):
    assert utils.money(0.1 + 0.2) == "S/ 0.30"
    assert utils.money(1234567.5) == "S/ 1,234,567.50"


def test_compute_stats_totals_are_clean(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-09-07")
    events = [{"date": "2026-09-07", "amount": 0.1} for _ in range(3)]
    s = utils.compute_stats(events)
    assert s["hoy"] == 0.3 and s["total_pendiente"] == 0.3


def test_weekly_buckets_totals_are_clean(utils, monkeypatch):
    monkeypatch.setattr(utils, "today_str", lambda: "2026-09-07")
    ws = utils.start_of_week("2026-09-07")
    events = [{"date": ws, "amount": 0.1} for _ in range(3)]
    buckets = utils.weekly_buckets(events, weeks_ahead=2)
    assert buckets[0]["amount"] == 0.3
    assert "_items" not in buckets[0]


def test_invoice_amount_stored_rounded(run_view, db):
    db.vendors.append({"id": 1, "name": "Bodega Sur", "ruc": "20999999999",
                       "doc_type": "contado", "term_days": None})
    from datetime import date
    at = run_view("views/1_Nueva_Factura.py", role="branch", branch="Sucursal 1")
    widget(at, "nf_query").set_value("Bodega Sur").run()
    widget(at, "nf_invoice_number").set_value("B-1").run()
    widget(at, "nf_amount", "number_input").set_value(10.005).run()
    widget(at, "nf_issue_date", "date_input").set_value(date(2026, 9, 1)).run()
    click(at, "Registrar documento")
    click(at, "Confirmar y guardar")
    assert db.invoices[0]["amount"] == 10.01


# ---------- #6: renombrar proveedor ----------

def test_rename_vendor_cascades_to_invoices(db):
    v = db.create_vendor({"name": "Droguería Norte", "ruc": "20123456789",
                          "doc_type": "credito", "term_days": 30})
    db.invoices.append({"id": "i1", "vendor": "Droguería Norte", "invoice_number": "F1",
                        "branch": "Sucursal 1", "doc_type": "credito", "amount": 100.0,
                        "issue_date": "2026-09-01", "due_date": "2026-10-01", "status": "pendiente"})
    db.update_vendor(v["id"], {"name": "Droguería del Norte SAC", "ruc": "20123456789",
                               "doc_type": "credito", "term_days": 30})
    assert db.vendors[0]["name"] == "Droguería del Norte SAC"
    assert db.invoices[0]["vendor"] == "Droguería del Norte SAC"


def test_rename_vendor_keeps_dup_check_consistent(db):
    """Tras renombrar, la factura histórica sigue apuntando al proveedor, así
    la validación de duplicados (que usa el nombre) no se rompe."""
    v = db.create_vendor({"name": "AAA", "ruc": "20111111111",
                          "doc_type": "contado", "term_days": None})
    db.invoices.append({"id": "i1", "vendor": "AAA", "invoice_number": "F1",
                        "branch": "Sucursal 1", "doc_type": "contado", "amount": 50.0,
                        "issue_date": "2026-09-01", "due_date": "2026-09-01", "status": "pendiente"})
    db.update_vendor(v["id"], {"name": "BBB", "ruc": "20111111111",
                               "doc_type": "contado", "term_days": None})
    same = [i for i in db.list_invoices() if i["vendor"] == "BBB" and i["invoice_number"] == "F1"]
    assert len(same) == 1
