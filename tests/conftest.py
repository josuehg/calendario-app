import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fake_db import FakeDB  # noqa: E402


@pytest.fixture
def db(monkeypatch):
    """Instala una BD en memoria como el módulo `db` y devuelve la instancia
    para sembrar datos y hacer asserts. `utils` se recarga para que tome
    esta versión."""
    fake = FakeDB()
    monkeypatch.setitem(sys.modules, "db", fake)
    if "utils" in sys.modules:
        importlib.reload(sys.modules["utils"])
    import utils  # noqa: F401
    yield fake
    monkeypatch.undo()
    if "utils" in sys.modules:
        importlib.reload(sys.modules["utils"])


@pytest.fixture
def run_view(db):
    """Corre una página de views/ con AppTest y el rol dado."""
    from streamlit.testing.v1 import AppTest

    def _run(path, role="admin", branch=None, **session):
        at = AppTest.from_file(str(ROOT / path), default_timeout=15)
        at.session_state["auth_role"] = role
        at.session_state["auth_branch"] = branch or ("Sucursal 1" if role == "branch" else None)
        for k, v in session.items():
            at.session_state[k] = v
        at.run()
        return at

    return _run


def widget(at, base, kind="text_input"):
    """Devuelve el widget cuya key empieza con `base` (ignora el sufijo nonce)."""
    for w in getattr(at, kind):
        if (getattr(w, "key", None) or "").startswith(base):
            return w
    return None


def click(at, label_contains):
    for b in at.button:
        if label_contains in b.label:
            return b.click().run()
    raise AssertionError(f"botón {label_contains!r} no está en {[b.label for b in at.button]}")
