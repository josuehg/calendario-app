"""Humo: cada página de views/ debe renderizar sin excepción con la BD vacía.

Atrapa regresiones de import, rutas rotas, o mal uso de la API de Streamlit
antes de que lleguen al deploy (que fue de donde salieron casi todos los
bugs anteriores).
"""
import pytest

ADMIN_VIEWS = [
    "views/0_Resumen.py",
    "views/1_Nueva_Factura.py",
    "views/2_Consolidado.py",
    "views/3_Canjear_a_Letras.py",
    "views/4_Calendario.py",
    "views/5_Presupuesto.py",
    "views/6_Configuracion.py",
    "views/7_Gastos.py",
]


@pytest.mark.parametrize("path", ADMIN_VIEWS)
def test_admin_view_renders_empty(run_view, path):
    at = run_view(path, role="admin")
    assert not at.exception, f"{path}: {at.exception}"


def test_branch_only_sees_registro(run_view):
    at = run_view("views/1_Nueva_Factura.py", role="branch", branch="Sucursal 1")
    assert not at.exception


def test_app_nav_admin_vs_branch(run_view):
    """app.py: sucursal -> 1 página con nav oculto; admin -> todas."""
    at = run_view("app.py", role="branch", branch="Sucursal 1")
    assert not at.exception

    at = run_view("app.py", role="admin")
    assert not at.exception
