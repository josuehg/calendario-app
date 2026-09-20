"""'Registrar letra ya programada': proveedor como desplegable de los ya
registrados, con opción de escribir uno nuevo si no está en la lista."""
from datetime import date

from tests.conftest import click

VIEW = "views/3_Canjear_a_Letras.py"


def _fill_and_submit(at, numero="L-1", monto=1000.0, venc=date(2026, 12, 1)):
    for ti in at.text_input:
        if ti.label == "N° de letra":
            ti.set_value(numero).run()
            break
    for ni in at.number_input:
        if ni.label == "Monto (S/)":
            ni.set_value(monto).run()
            break
    for di in at.date_input:
        if di.label == "Vencimiento":
            di.set_value(venc).run()
            break
    return click(at, "Registrar letra")


def test_proveedor_dropdown_lists_registered_vendors(run_view, db):
    db.create_vendor({"name": "Droguería Norte", "ruc": None, "doc_type": "credito", "term_days": 30})
    db.create_vendor({"name": "Bodega Sur", "ruc": None, "doc_type": "contado", "term_days": None})
    at = run_view(VIEW, role="admin")
    sb = next(s for s in at.selectbox if s.key == "ld_vendor_pick")
    assert "Droguería Norte" in sb.options and "Bodega Sur" in sb.options


def test_registrar_con_proveedor_de_la_lista(run_view, db):
    db.create_vendor({"name": "Droguería Norte", "ruc": None, "doc_type": "credito", "term_days": 30})
    at = run_view(VIEW, role="admin")
    for sb in at.selectbox:
        if sb.key == "ld_vendor_pick":
            sb.set_value("Droguería Norte").run()
            break
    at = _fill_and_submit(at)
    assert not at.exception
    assert db.letras and db.letras[0]["vendor"] == "Droguería Norte"


def test_registrar_con_proveedor_nuevo_escrito_a_mano(run_view, db):
    at = run_view(VIEW, role="admin")
    for ti in at.text_input:
        if ti.key == "ld_vendor_new":
            ti.set_value("Proveedor Suelto SAC").run()
            break
    at = _fill_and_submit(at)
    assert not at.exception
    assert db.letras and db.letras[0]["vendor"] == "Proveedor Suelto SAC"


def test_texto_nuevo_tiene_prioridad_sobre_la_lista(run_view, db):
    db.create_vendor({"name": "Droguería Norte", "ruc": None, "doc_type": "credito", "term_days": 30})
    at = run_view(VIEW, role="admin")
    for sb in at.selectbox:
        if sb.key == "ld_vendor_pick":
            sb.set_value("Droguería Norte").run()
            break
    for ti in at.text_input:
        if ti.key == "ld_vendor_new":
            ti.set_value("Otro Proveedor").run()
            break
    at = _fill_and_submit(at)
    assert db.letras and db.letras[0]["vendor"] == "Otro Proveedor"


def test_sin_proveedor_elegido_ni_escrito_muestra_error(run_view, db):
    at = run_view(VIEW, role="admin")
    at = _fill_and_submit(at)
    assert any("proveedor" in e.value.lower() for e in at.error)
    assert not db.letras
