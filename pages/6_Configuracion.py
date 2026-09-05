import streamlit as st
import db
import utils

st.title("⚙️ Configuración")

# ---------- sucursales y PIN ----------
st.subheader("Sucursales y PIN de acceso")
st.caption(
    "Cada sucursal entra a la app con su propio PIN — así queda identificada "
    "automáticamente, sin tener que elegirla de una lista. Usa PINs distintos entre sí "
    "y distintos del PIN de administrador."
)

branches = db.get_branches_full()
while len(branches) < 6:
    branches.append({"name": f"Sucursal {len(branches) + 1}", "pin": ""})

with st.form("branches_form"):
    rows = []
    for i, b in enumerate(branches):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input(f"Sucursal {i + 1}", value=b["name"], key=f"branch_name_{i}")
        pin = c2.text_input(f"PIN {i + 1}", value=b.get("pin") or "", key=f"branch_pin_{i}", type="password")
        rows.append({"name": name, "pin": pin})
    submitted = st.form_submit_button("Guardar sucursales", type="primary")
    if submitted:
        pins = [r["pin"].strip() for r in rows if r["pin"].strip()]
        if len(pins) != len(set(pins)):
            st.error("Hay PINs repetidos entre sucursales — cada una necesita uno distinto.")
        else:
            db.save_branches(rows)
            st.success("Sucursales guardadas.")

st.divider()

# ---------- proveedores ----------
st.subheader("Proveedores: contado o crédito")
st.caption(
    "Configura aquí cómo trabajas con cada proveedor. Cuando una sucursal registre una "
    "factura de este proveedor, el tipo y el plazo se aplican solos — ellas ya no lo eligen."
)

vendors = db.get_vendors()

if vendors:
    for v in vendors:
        c1, c2, c3, c4 = st.columns([2, 1.2, 1, 0.7])
        c1.write(f"**{v['name']}**")
        c2.write("Crédito" if v["doc_type"] == "credito" else "Contado")
        c3.write(f"{v['term_days']} días" if v["doc_type"] == "credito" and v["term_days"] else "—")
        if c4.button("Editar", key=f"edit_vendor_{v['id']}"):
            st.session_state["_edit_vendor"] = v
            st.rerun()
else:
    st.caption("Aún no has registrado proveedores.")

st.divider()
st.markdown("**" + ("Editar proveedor" if st.session_state.get("_edit_vendor") else "Agregar proveedor") + "**")

editing = st.session_state.get("_edit_vendor")
with st.form("vendor_form", clear_on_submit=not editing):
    name = st.text_input("Nombre del proveedor", value=editing["name"] if editing else "")
    doc_type = st.radio(
        "Tipo", ["contado", "credito"],
        index=(1 if editing and editing["doc_type"] == "credito" else 0),
        format_func=lambda x: "Contado" if x == "contado" else "Crédito", horizontal=True,
    )
    term_days = None
    if doc_type == "credito":
        default_term = editing["term_days"] if editing and editing.get("term_days") in utils.TERM_OPTIONS else utils.TERM_OPTIONS[0]
        term_days = st.selectbox("Plazo", utils.TERM_OPTIONS, index=utils.TERM_OPTIONS.index(default_term), format_func=lambda d: f"{d} días")
    c1, c2 = st.columns(2)
    save = c1.form_submit_button("Guardar proveedor", type="primary")
    cancel = c2.form_submit_button("Cancelar edición") if editing else False

    if save:
        if not name.strip():
            st.error("Ponle un nombre al proveedor.")
        else:
            db.save_vendor({"name": name.strip(), "doc_type": doc_type, "term_days": term_days})
            st.session_state["_edit_vendor"] = None
            st.success("Proveedor guardado.")
            st.rerun()
    if cancel:
        st.session_state["_edit_vendor"] = None
        st.rerun()

if editing:
    if st.button("🗑️ Eliminar este proveedor"):
        db.delete_vendor(editing["id"])
        st.session_state["_edit_vendor"] = None
        st.success("Proveedor eliminado.")
        st.rerun()
