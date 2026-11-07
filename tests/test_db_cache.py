"""Caché de lecturas de db.py (el resto de las pruebas usan FakeDB): las
lecturas repetidas no vuelven a consultar Supabase, y cualquier escritura
las invalida. También la lectura de secretos desde variables de entorno."""
import importlib
import sys

import pytest


class _Query:
    def __init__(self, client, table):
        self.client, self.table = client, table

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        self.client.calls.append(self.table)
        return type("R", (), {"data": list(self.client.rows.get(self.table, []))})()


class _Client:
    def __init__(self):
        self.calls, self.rows = [], {"invoices": [{"id": 1}]}

    def table(self, name):
        return _Query(self, name)


@pytest.fixture
def real_db(monkeypatch):
    monkeypatch.delitem(sys.modules, "db", raising=False)
    db = importlib.import_module("db")
    client = _Client()
    monkeypatch.setattr(db, "get_client", lambda: client)
    import streamlit as st
    st.cache_data.clear()
    yield db, client
    st.cache_data.clear()
    sys.modules.pop("db", None)


def test_lectura_repetida_no_vuelve_a_consultar(real_db):
    db, client = real_db
    assert db.list_invoices() == [{"id": 1}]
    assert db.list_invoices() == [{"id": 1}]
    assert client.calls == ["invoices"]


def test_escritura_invalida_las_lecturas(real_db):
    db, client = real_db
    db.list_invoices()
    client.rows["invoices"].append({"id": 2})
    db.update_invoice("1", {"amount": 5})
    assert db.list_invoices() == [{"id": 1}, {"id": 2}]
    assert client.calls == ["invoices", "invoices", "invoices"]


def test_escritura_permite_generar_cuotas_de_un_gasto_fijo_nuevo(real_db, monkeypatch):
    # Bug real: ensure_expense_instances corría una vez por sesión y día, así
    # que un gasto fijo creado después no generaba sus cuotas hasta mañana.
    db, _client = real_db
    import streamlit as st
    estado = {"_instancias_gastos_ok": "2026-11-06"}
    monkeypatch.setattr(st, "session_state", estado)
    db.create_fixed_expense({"name": "BCP 150K"})
    assert "_instancias_gastos_ok" not in estado


def test_secreto_desde_variable_de_entorno(monkeypatch):
    import utils
    monkeypatch.setenv("SECRETO_DE_PRUEBA", "abc")
    assert utils.secret("SECRETO_DE_PRUEBA") == "abc"
    assert utils.secret("NO_EXISTE_XYZ", "x") == "x"
