import streamlit as st
import db
import utils

st.title("⚙️ Configuración")

# ---------- enfoque contado/crédito ----------
st.subheader("Enfoque del sistema")
settings = db.get_settings()
track_contado = st.toggle(
    "Registrar y mostrar compras al contado",
    value=settings.get("track_contado", True),
    help=(
        "Si lo apagas, las compras al contado se siguen registrando y ves todas en "
        "Consolidado, pero dejan de aparecer en Resumen, Calendario y Presupuesto — "
        "así esas vistas quedan enfocadas solo en las cuentas por pagar (crédito)."
    ),
)
if track_contado != settings.get("track_contado", True):
    db.save_settings({"track_contado": track_contado})
    st.success("Guardado.")
    st.rerun()

st.divider()

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

search = st.text_input("🔎 Buscar proveedor (nombre o RUC)")
vendors = db.get_vendors()
if search:
    s = search.strip().lower()
    vendors = [v for v in vendors if s in v["name"].lower() or s in (v.get("ruc") or "").lower()]

if vendors:
    h1, h2, h3, h4, h5 = st.columns([1.8, 1, 1.1, 1, 0.7])
    h1.markdown("**Proveedor**")
    h2.markdown("**RUC**")
    h3.markdown("**Tipo**")
    h4.markdown("**Plazo**")
    for v in vendors:
        c1, c2, c3, c4, c5 = st.columns([1.8, 1, 1.1, 1, 0.7])
        c1.write(v["name"])
        c2.write(v.get("ruc") or "—")
        c3.write("Crédito" if v["doc_type"] == "credito" else "Contado")
        c4.write(f"{v['term_days']} días" if v["doc_type"] == "credito" and v["term_days"] else "—")
        if c5.button("Editar", key=f"edit_vendor_{v['id']}"):
            st.session_state["_edit_vendor"] = v
            st.rerun()
elif search:
    st.caption("No se encontró ningún proveedor con ese criterio.")
else:
    st.caption("Aún no has registrado proveedores.")

st.divider()
editing = st.session_state.get("_edit_vendor")
st.markdown("**" + ("Editar proveedor" if editing else "Agregar proveedor") + "**")

# Fuera de un st.form a propósito: así el campo "Plazo" aparece al instante
# apenas eliges "Crédito", en vez de esperar a que le des a Guardar.
name = st.text_input("Nombre del proveedor", value=editing["name"] if editing else "", key="vendor_name_input")
ruc = st.text_input("RUC (opcional)", value=(editing.get("ruc") or "") if editing else "", key="vendor_ruc_input", max_chars=11)
doc_type = st.radio(
    "Tipo", ["contado", "credito"],
    index=(1 if editing and editing["doc_type"] == "credito" else 0),
    format_func=lambda x: "Contado" if x == "contado" else "Crédito", horizontal=True,
    key="vendor_doctype_input",
)
term_days = None
if doc_type == "credito":
    default_term = editing["term_days"] if editing and editing.get("term_days") in utils.TERM_OPTIONS else utils.TERM_OPTIONS[0]
    term_days = st.selectbox(
        "Plazo", utils.TERM_OPTIONS, index=utils.TERM_OPTIONS.index(default_term),
        format_func=lambda d: f"{d} días", key="vendor_term_input",
    )

c1, c2 = st.columns(2)
if c1.button("Guardar proveedor", type="primary"):
    if not name.strip():
        st.error("Ponle un nombre al proveedor.")
    else:
        db.save_vendor({
            "name": name.strip(),
            "ruc": ruc.strip() or None,
            "doc_type": doc_type,
            "term_days": term_days,
        })
        st.session_state["_edit_vendor"] = None
        if not editing:
            for k in ["vendor_name_input", "vendor_ruc_input", "vendor_doctype_input", "vendor_term_input"]:
                st.session_state.pop(k, None)
        st.success("Proveedor guardado.")
        st.rerun()

if editing:
    if c2.button("Cancelar edición"):
        st.session_state["_edit_vendor"] = None
        st.rerun()
    if st.button("🗑️ Eliminar este proveedor"):
        db.delete_vendor(editing["id"])
        st.session_state["_edit_vendor"] = None
        st.success("Proveedor eliminado.")
        st.rerun()
