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


def test_no_hay_seccion_de_atrasados_si_no_hay_nada_vencido(tdr):
    text = tdr.build_message("2026-10-26")
    assert "Atrasados" not in text


def test_factura_vencida_aparece_en_atrasados_con_dias(tdr, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov Vieja", "invoice_number": "F-3",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 80.0,
        "issue_date": "2026-09-01", "due_date": "2026-10-20", "status": "pendiente",
    })
    text = tdr.build_message("2026-10-26")
    assert "⚠️ Atrasados" in text
    assert "Prov Vieja" in text and "6 día(s) de atraso" in text
    assert "Total atrasado: S/ 80.00" in text


def test_letra_atrasada_cuenta_desde_el_limite_no_desde_la_fecha_esperada(tdr, db):
    # vencimiento 01-10, plazo típico 8 (fecha esperada 09-10), gracia máx 10
    # (límite real 11-10). Hoy 21-10: el atraso debe contarse desde el límite
    # (10 días), no desde la fecha esperada (12 días).
    db.create_letra({"numero": "L-2", "monto": 500.0, "fecha_vencimiento": "2026-10-01",
                     "vendor": "Prov Letra Vieja", "branch": "Sucursal 1"})
    text = tdr.build_message("2026-10-21")
    assert "Prov Letra Vieja" in text
    assert "10 día(s) de atraso" in text


def test_avisa_de_sucursales_sin_ingreso_de_ayer(tdr, db):
    text = tdr.build_message("2026-10-26")
    assert "Falta registrar el ingreso de ayer" in text
    assert "Sucursal 1" in text and "Sucursal 2" in text and "Sucursal 3" in text


def test_no_avisa_si_todas_registraron_ingreso_de_ayer(tdr, db):
    for b in db.get_branches():
        db.create_income({"branch": b, "date": "2026-10-25", "amount": 100.0})
    text = tdr.build_message("2026-10-26")
    assert "Falta registrar" not in text


def test_avisa_solo_de_las_sucursales_que_faltan(tdr, db):
    db.create_income({"branch": "Sucursal 1", "date": "2026-10-25", "amount": 100.0})
    text = tdr.build_message("2026-10-26")
    assert "Falta registrar" in text
    linea = next(l for l in text.splitlines() if "Falta registrar" in l)
    assert "Sucursal 1" not in linea
    assert "Sucursal 2" in linea and "Sucursal 3" in linea


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
