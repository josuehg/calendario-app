"""En Letras → Todas las letras, el vencimiento se marca igual que en
Calendario: rojo recién pasado el plazo máximo (con el atraso contado desde el
vencimiento) y, antes de eso, "en plazo"."""
from datetime import date, timedelta

VIEW = "views/3_Canjear_a_Letras.py"


def _letra(db, numero, dias_desde_vencimiento):
    db.create_letra({"numero": numero, "monto": 100.0, "vendor": "Prov", "branch": "Sucursal 1",
                     "fecha_vencimiento": (date.today() - timedelta(days=dias_desde_vencimiento)).isoformat()})


def test_vencida_pasado_el_plazo_sale_en_rojo_con_dias_desde_el_vencimiento(run_view, db):
    _letra(db, "L-1", 12)  # plazo máximo 10 en FakeDB
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    assert "🔴" in text and "12 días de atraso" in text


def test_vencida_dentro_del_plazo_no_sale_en_rojo(run_view, db):
    _letra(db, "L-1", 3)
    at = run_view(VIEW, role="admin")
    assert not at.exception
    text = " ".join(str(m.value) for m in at.markdown)
    limite = (date.today() + timedelta(days=7)).strftime("%d/%m/%y")
    assert "🔴" not in text and f"en plazo hasta {limite}" in text
