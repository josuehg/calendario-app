import importlib
import sys

import pytest


@pytest.fixture
def tdr(db):
    """Importa (o recarga) el script, para que tome la FakeDB ya instalada
    en sys.modules['db'] por el fixture `db`."""
    name = "scripts.telegram_daily_report"
    if name in sys.modules:
        module = importlib.reload(sys.modules[name])
    else:
        module = importlib.import_module(name)
    return module


def test_sin_pagos_hoy_avisa_que_no_hay_nada(tdr):
    text = tdr.build_message("2026-10-26")
    assert "No hay pagos programados para hoy" in text


def test_agrupa_pagos_del_dia_con_total(tdr, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 150.0,
        "issue_date": "2026-10-01", "due_date": "2026-10-26", "status": "pendiente",
    })
    db.create_letra({"numero": "L-1", "monto": 300.0, "fecha_vencimiento": "2026-10-18",
                     "vendor": "Prov Letra", "branch": "Sucursal 2"})  # 18 + 8 = 26
    text = tdr.build_message("2026-10-26")
    assert "Prov A" in text and "S/ 150.00" in text
    assert "Prov Letra" in text and "S/ 300.00" in text
    assert "Total del día: S/ 450.00" in text


def test_no_incluye_pagos_de_otro_dia(tdr, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Mañana", "invoice_number": "F-2",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 99.0,
        "issue_date": "2026-10-01", "due_date": "2026-10-27", "status": "pendiente",
    })
    text = tdr.build_message("2026-10-26")
    assert "Prov Mañana" not in text


def test_send_telegram_llama_a_la_api_con_el_texto(tdr, monkeypatch):
    llamadas = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"ok"

    def _fake_urlopen(req, timeout=15):
        llamadas.append(req.full_url if hasattr(req, "full_url") else req)
        return _FakeResp()

    monkeypatch.setattr(tdr.urllib.request, "urlopen", _fake_urlopen)
    tdr.send_telegram("hola", "TOKEN123", "-100555")
    assert len(llamadas) == 1
    assert "TOKEN123" in llamadas[0]
