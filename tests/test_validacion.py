"""Rol 'Validador': un PIN compartido para todas las sucursales que solo
confirma (cruce manual contra Odoo) que las facturas ya estén registradas,
sin poder editar, pagar ni eliminar nada."""
import pathlib

from streamlit.testing.v1 import AppTest

from tests.conftest import click

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEW = "views/8_Validacion.py"


def _login(pin, admin_pin="admin123", validator_pin="val123"):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)
    at.secrets["APP_PASSWORD"] = admin_pin
    at.secrets["VALIDATOR_PASSWORD"] = validator_pin
    at.run()
    for ti in at.text_input:
        if ti.label == "PIN":
            ti.set_value(pin).run()
            break
    for b in at.button:
        if b.label == "Entrar":
            b.click().run()
            break
    return at


def test_validator_pin_logs_in_as_validador(db):
    at = _login("val123")
    assert not at.exception
    assert at.session_state["auth_role"] == "validador"
    assert at.session_state["auth_branch"] is None


def test_wrong_pin_shows_error(db):
    at = _login("no-existe")
    assert any("PIN incorrecto" in e.value for e in at.error)
    assert "auth_role" not in at.session_state


def test_validador_only_sees_validacion_page(run_view, db):
    at = run_view("app.py", role="validador")
    assert not at.exception
    assert any("Validación de facturas" in str(t.value) for t in at.title)


# ---------- pantalla de validación ----------

def _seed(db):
    db.create_invoice({
        "branch": "Sucursal 1", "vendor": "Droguería Norte", "invoice_number": "F-1",
        "document_type": "Factura", "doc_type": "credito", "amount": 100.0,
        "issue_date": "2026-09-01", "due_date": "2026-10-01", "status": "pendiente",
    })
    db.create_invoice({
        "branch": "Sucursal 2", "vendor": "Bodega Sur", "invoice_number": "F-2",
        "document_type": "Nota de compra", "doc_type": "contado", "amount": 50.0,
        "issue_date": "2026-09-02", "due_date": "2026-09-02", "status": "pendiente",
    })


def test_lists_pending_and_counts(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="validador")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Pendientes de validar (todas las sucursales)") == "2"
    text = " ".join(str(m.value) for m in at.markdown)
    assert "Droguería Norte" in text and "Bodega Sur" in text


def test_marcar_validado_records_who_and_when(run_view, db):
    _seed(db)
    at = run_view(VIEW, role="validador")
    click(at, "Marcar validado")
    assert not at.exception
    validated = [i for i in db.invoices if i.get("validated")]
    assert len(validated) == 1
    assert validated[0]["validated_by"] == "Validador"
    assert validated[0]["validated_at"]


def test_filtro_solo_pendientes_oculta_validados(run_view, db):
    _seed(db)
    db.mark_invoice_validated(db.invoices[0]["id"], "Validador", "2026-09-05")
    at = run_view(VIEW, role="validador")
    for sb in at.selectbox:
        if sb.key == "val_f_validado":
            sb.set_value("Pendientes de validar").run()
            break
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Mostrando con estos filtros") == "1"


def test_desmarcar_vuelve_a_pendiente(run_view, db):
    _seed(db)
    db.mark_invoice_validated(db.invoices[0]["id"], "Validador", "2026-09-05")
    at = run_view(VIEW, role="validador")
    click(at, "Desmarcar")
    assert not at.exception
    assert not any(i.get("validated") for i in db.invoices)


def test_consolidado_shows_validado_column(run_view, db):
    _seed(db)
    db.mark_invoice_validated(db.invoices[0]["id"], "Validador", "2026-09-05")
    at = run_view("views/2_Consolidado.py", role="admin")
    df = at.dataframe[0].value
    assert "Validado" in list(df.columns)
    assert "✅" in df["Validado"].tolist()
    assert "—" in df["Validado"].tolist()
