"""'Canjear facturas a letras' (pestaña de selección): la multiselección de
facturas debía tener key fija (sin ella, Streamlit a veces 'olvidaba' lo ya
elegido entre recargas) y un filtro por proveedor para agrupar más rápido
varias facturas del mismo proveedor en una letra."""
from tests.conftest import click

VIEW = "views/3_Canjear_a_Letras.py"


def _seed_pendientes(db):
    db.invoices.append({"id": "i1", "vendor": "Representaciones Castillo", "invoice_number": "F-1",
                        "branch": "Sucursal 1", "doc_type": "credito", "amount": 100.0,
                        "due_date": "2026-11-01", "issue_date": "2026-09-01", "status": "pendiente"})
    db.invoices.append({"id": "i2", "vendor": "Representaciones Castillo", "invoice_number": "F-2",
                        "branch": "Sucursal 1", "doc_type": "credito", "amount": 200.0,
                        "due_date": "2026-11-02", "issue_date": "2026-09-01", "status": "pendiente"})
    db.invoices.append({"id": "i3", "vendor": "Otro Proveedor", "invoice_number": "F-3",
                        "branch": "Sucursal 2", "doc_type": "credito", "amount": 300.0,
                        "due_date": "2026-11-03", "issue_date": "2026-09-01", "status": "pendiente"})
    return db


def _select(at, labels):
    for ms in at.multiselect:
        if ms.key == "canje_multiselect":
            ms.set_value(labels).run()
            return
    raise AssertionError("no se encontró el multiselect canje_multiselect")


def test_multiselect_has_stable_key(run_view, db):
    _seed_pendientes(db)
    at = run_view(VIEW, role="admin")
    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    assert ms is not None


def test_selection_survives_a_rerun_triggered_elsewhere(run_view, db):
    """Regresión: sin key fija, una recarga disparada por otro widget (ej. el
    filtro de proveedor) podía perder lo ya elegido."""
    _seed_pendientes(db)
    at = run_view(VIEW, role="admin")
    label_i1 = next(l for l in next(m for m in at.multiselect if m.key == "canje_multiselect").options if "F-1" in l)
    _select(at, [label_i1])
    assert at.session_state["canje_selected_ids"] == ["i1"]

    # Dispara otro rerun (filtro), sin tocar el multiselect directamente.
    for ti in at.text_input:
        if ti.key == "canje_f_vendor":
            ti.set_value("Otro Proveedor").run()
            break
    assert at.session_state["canje_selected_ids"] == ["i1"]


def test_filtro_proveedor_mantiene_lo_elegido_fuera_del_filtro(run_view, db):
    _seed_pendientes(db)
    at = run_view(VIEW, role="admin")
    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    label_i1 = next(l for l in ms.options if "F-1" in l)
    _select(at, [label_i1])

    for ti in at.text_input:
        if ti.key == "canje_f_vendor":
            ti.set_value("Otro Proveedor").run()
            break

    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    assert any("F-1" in l for l in ms.options)   # i1 sigue visible aunque no sea "Otro Proveedor"
    assert any("F-3" in l for l in ms.options)   # y F-3 aparece por el filtro
    assert not any("F-2" in l for l in ms.options)  # F-2 no, ni coincide ni está elegida


def test_filtro_proveedor_reduce_opciones(run_view, db):
    _seed_pendientes(db)
    at = run_view(VIEW, role="admin")
    for ti in at.text_input:
        if ti.key == "canje_f_vendor":
            ti.set_value("Castillo").run()
            break
    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    assert len(ms.options) == 2
    assert all("Castillo" in l for l in ms.options)


def test_preselect_desde_consolidado_se_aplica(run_view, db):
    _seed_pendientes(db)
    at = run_view(VIEW, role="admin", canje_preselect=["i1", "i2"])
    assert at.session_state["canje_selected_ids"] == ["i1", "i2"]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Total de facturas seleccionadas") == "S/ 300.00"


def test_preselect_se_reaplica_aunque_ya_hubiera_seleccion_previa(run_view, db):
    """Regresión: si ya se había usado la pestaña antes en la sesión (el
    multiselect ya tiene su propio estado por key), un nuevo 'Canjear
    seleccionadas' desde Consolidado se quedaba pegado con la selección
    vieja en vez de tomar la preselección nueva."""
    _seed_pendientes(db)
    at = run_view(
        VIEW, role="admin",
        canje_selected_ids=["i3"], canje_multiselect=[],   # estado "ya usado antes" en la sesión
        canje_preselect=["i1"],                            # llega un nuevo preselect de Consolidado
    )
    assert at.session_state["canje_selected_ids"] == ["i1"]
    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    assert any("F-1" in l for l in ms.value)


def test_confirmar_canje_limpia_seleccion_para_el_siguiente(run_view, db):
    _seed_pendientes(db)
    # Una factura más, que no se selecciona — así el multiselect sigue
    # renderizándose después de confirmar (si no, pendientes_credito queda
    # vacío y no hay nada que comprobar).
    db.invoices.append({"id": "i4", "vendor": "Otro Proveedor", "invoice_number": "F-4",
                        "branch": "Sucursal 2", "doc_type": "credito", "amount": 50.0,
                        "due_date": "2026-11-05", "issue_date": "2026-09-01", "status": "pendiente"})
    at = run_view(VIEW, role="admin")
    label_i1 = next(l for l in next(m for m in at.multiselect if m.key == "canje_multiselect").options if "F-1" in l)
    _select(at, [label_i1])

    for ni in at.number_input:
        if ni.label.startswith("Monto"):
            ni.set_value(100.0)
            break
    for di in at.date_input:
        if di.label.startswith("Vencimiento"):
            di.set_value(__import__("datetime").date(2026, 12, 1))
            break
    click(at, "Revisar y confirmar canje")
    click(at, "Confirmar y guardar")

    assert not at.exception
    assert db.canjes
    assert at.session_state["canje_selected_ids"] == []
    ms = next(m for m in at.multiselect if m.key == "canje_multiselect")
    assert ms.value == []
