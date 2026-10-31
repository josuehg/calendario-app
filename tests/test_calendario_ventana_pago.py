"""Marca visual de la 'ventana de pago' de una letra en el grid de Calendario
(día de vencimiento real + día límite de gracia), sin alterar los totales
de ningún día — es solo una referencia, no suma montos."""
from datetime import date

from tests.conftest import click

VIEW = "views/4_Calendario.py"


def test_dia_de_vencimiento_muestra_marca_sin_sumar_monto(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-10",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    # El vencimiento real (10) debe traer la marca 🧾, pero el total de ese
    # día no debe incluir el monto (la letra "vive" en el 10+8=18).
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🧾" in text
    # El total del mes (KPI) no debe incluir el monto en el día de vencimiento
    # real (10) -- la letra "vive" para efectos de monto en el 10+8=18, y el
    # total del mes sigue siendo el mismo monto una sola vez.
    total_mes = next(m.value for m in at.metric if m.label == "Total del mes")
    assert total_mes == "S/ 500.00"


def test_dia_limite_muestra_marca_de_reloj(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-10",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    text = " ".join(str(m.value) for m in at.markdown)
    assert "⏰" in text


def test_marca_dice_de_que_letra_es_al_pasar_el_mouse(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-10",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    db.create_letra({"numero": "L-2", "monto": 300.0, "fecha_vencimiento": "2020-01-10",
                     "vendor": "O'Brien & Cía", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🧾 2" in text
    assert "Vence: Prov Letra · Letra L-1 · S/ 500.00" in text
    # Un apóstrofe sin escapar cerraría el atributo title antes de tiempo.
    assert "Vence: O&#x27;Brien &amp; Cía · Letra L-2 · S/ 300.00" in text
    assert "Límite de pago: Prov Letra · Letra L-1 · S/ 500.00" in text


def test_dia_dialogo_muestra_vence_y_limite(run_view, db):
    db.create_letra({"numero": "L-1", "monto": 500.0, "fecha_vencimiento": "2020-01-10",
                     "vendor": "Prov Letra", "branch": "Sucursal 1"})
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1, _cal_day="2020-01-18")
    assert not at.exception
    caps = " ".join(str(c.value) for c in at.caption)
    assert "Vence: 10/01/20" in caps
    assert "Límite de pago: 20/01/20" in caps


def test_marca_respeta_filtro_de_tipo(run_view, db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Prov A", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "term_days": 30, "amount": 100.0,
        "issue_date": "2020-01-01", "due_date": "2020-01-10", "status": "pendiente",
    })
    at = run_view(VIEW, role="admin", cal_year=2020, cal_month=1)
    for sb in at.selectbox:
        if sb.key == "cal_f_tipo":
            sb.set_value("Facturas a crédito").run()
            break
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🧾" not in text and "⏰" not in text
