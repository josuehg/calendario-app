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
    "factura de este proveedor, el tipo y el plazo se aplican solos — ellas ya no lo eligen. "
    "Las sucursales también pueden crear un proveedor nuevo desde Nueva Factura si no existe todavía; "
    "aquí puedes revisarlo y ajustarle el tipo y el plazo."
)

top1, top2 = st.columns([3, 1])
search = top1.text_input(
    "Buscar proveedor", label_visibility="collapsed",
    placeholder="🔎 Buscar proveedor por nombre o RUC",
)
if top2.button("➕ Nuevo proveedor", use_container_width=True):
    st.session_state["_vendor_dialog"] = {"mode": "new", "data": None}
    st.rerun()

vendors = db.get_vendors()
if search:
    s = search.strip().lower()
    vendors = [v for v in vendors if s in v["name"].lower() or s in (v.get("ruc") or "").lower()]

if vendors:
    for v in vendors:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.6, 0.9])
            with c1:
                st.markdown(f"**{v['name']}**")
                st.caption(f"RUC {v['ruc']}" if v.get("ruc") else "Sin RUC registrado")
            with c2:
                if v["doc_type"] == "credito":
                    st.markdown(f"🟢 Crédito · {v['term_days']} días" if v.get("term_days") else "🟢 Crédito")
                else:
                    st.markdown("⚪ Contado")
            with c3:
                if st.button("Editar", key=f"edit_vendor_{v['id']}", use_container_width=True):
                    st.session_state["_vendor_dialog"] = {"mode": "edit", "data": v}
                    st.rerun()
elif search:
    st.caption("No se encontró ningún proveedor con ese criterio.")
else:
    st.caption("Aún no has registrado proveedores. Usa \"➕ Nuevo proveedor\" para empezar.")

# ---------- dialog: nuevo / editar proveedor ----------
dialog_state = st.session_state.get("_vendor_dialog")
if dialog_state:
    editing = dialog_state.get("data")

    @st.dialog("Editar proveedor" if editing else "Nuevo proveedor")
    def _vendor_dialog():
        name = st.text_input("Nombre del proveedor", value=editing["name"] if editing else "", key="vd_name")
        ruc = st.text_input(
            "RUC (opcional)", value=(editing.get("ruc") or "") if editing else "",
            key="vd_ruc", max_chars=11,
        )
        doc_type = st.radio(
            "Tipo", ["contado", "credito"],
            index=(1 if editing and editing["doc_type"] == "credito" else 0),
            format_func=lambda x: "Contado" if x == "contado" else "Crédito", horizontal=True,
            key="vd_doctype",
        )
        term_days = None
        if doc_type == "credito":
            default_term = (
                editing["term_days"]
                if editing and editing.get("term_days") in utils.TERM_OPTIONS
                else utils.TERM_OPTIONS[0]
            )
            term_days = st.selectbox(
                "Plazo", utils.TERM_OPTIONS, index=utils.TERM_OPTIONS.index(default_term),
                format_func=lambda d: f"{d} días", key="vd_term",
            )

        st.divider()
        b1, b2 = st.columns(2)
        if b1.button("Guardar", type="primary", use_container_width=True):
            name_clean = name.strip()
            ruc_clean = ruc.strip() or None
            name_l = name_clean.lower()

            all_vendors = db.get_vendors()
            other_vendors = [v for v in all_vendors if not editing or v["id"] != editing["id"]]
            name_conflict = next((v for v in other_vendors if v["name"].strip().lower() == name_l), None)
            ruc_conflict = (
                next((v for v in other_vendors if (v.get("ruc") or "") == ruc_clean), None)
                if ruc_clean else None
            )

            if not name_clean:
                st.error("Ponle un nombre al proveedor.")
            elif name_conflict:
                st.error(f"Ya existe un proveedor llamado **{name_conflict['name']}**. Usa un nombre distinto o edita ese proveedor.")
            elif ruc_conflict:
                st.error(f"El RUC {ruc_clean} ya está asignado a **{ruc_conflict['name']}**. Verifica el RUC.")
            else:
                try:
                    payload = {"name": name_clean, "ruc": ruc_clean, "doc_type": doc_type, "term_days": term_days}
                    if editing:
                        db.update_vendor(editing["id"], payload)
                    else:
                        db.create_vendor(payload)
                except Exception:
                    st.error("No se pudo guardar: el nombre o el RUC ya está en uso por otro proveedor.")
                else:
                    st.session_state["_vendor_dialog"] = None
                    for k in ["vd_name", "vd_ruc", "vd_doctype", "vd_term", "_confirm_del_vendor"]:
                        st.session_state.pop(k, None)
                    st.success("Proveedor guardado.")
                    st.rerun()
        if b2.button("Cancelar", use_container_width=True):
            st.session_state["_vendor_dialog"] = None
            st.session_state.pop("_confirm_del_vendor", None)
            st.rerun()

        if editing:
            st.divider()
            if not st.session_state.get("_confirm_del_vendor"):
                if st.button("🗑️ Eliminar este proveedor"):
                    st.session_state["_confirm_del_vendor"] = True
                    st.rerun()
            else:
                st.warning("¿Seguro que quieres eliminar este proveedor? Esta acción no se puede deshacer.")
                d1, d2 = st.columns(2)
                if d1.button("Sí, eliminar", type="primary", use_container_width=True):
                    db.delete_vendor(editing["id"])
                    st.session_state["_vendor_dialog"] = None
                    st.session_state.pop("_confirm_del_vendor", None)
                    st.success("Proveedor eliminado.")
                    st.rerun()
                if d2.button("No, cancelar", use_container_width=True):
                    st.session_state["_confirm_del_vendor"] = False
                    st.rerun()

    _vendor_dialog()
