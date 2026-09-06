import streamlit as st
import db
import utils

st.title("🧾 Registrar factura")

auth_role = st.session_state.get("auth_role")
auth_branch = st.session_state.get("auth_branch")

DOCUMENT_TYPES = ["Factura", "Boleta", "Nota de compra", "Otro"]

if auth_role == "branch":
    st.text_input("Sucursal", value=auth_branch, disabled=True)
    branch = auth_branch
else:
    branch = st.selectbox("Sucursal", db.get_branches() + ["Oficina central"])

st.markdown("**Proveedor**")
query = st.text_input(
    "Buscar proveedor por RUC o nombre",
    key="nf_query",
    placeholder="Ej: 20123456789 o 'Droguería Norte'",
)

matched_vendor = None
vendor_name = None
doc_type = None
term_days = None
is_new_vendor = False
new_vendor_ruc = ""

q = query.strip()
if q:
    all_vendors = db.get_vendors()
    ql = q.lower()

    if q.isdigit():
        exact = next((v for v in all_vendors if (v.get("ruc") or "") == q), None)
        candidates = [exact] if exact else [v for v in all_vendors if ql in (v.get("ruc") or "").lower()]
    else:
        candidates = [v for v in all_vendors if ql in v["name"].lower() or ql in (v.get("ruc") or "").lower()]

    if len(candidates) == 1:
        matched_vendor = candidates[0]
    elif len(candidates) > 1:
        options = {f"{v['name']} · RUC {v.get('ruc') or 's/RUC'}": v for v in candidates}
        choice = st.selectbox(
            "Se encontraron varios proveedores, elige el correcto:",
            list(options.keys()),
            key=f"nf_vendor_choice_{q}",
        )
        matched_vendor = options[choice]

    if matched_vendor:
        ruc_txt = f" · RUC {matched_vendor['ruc']}" if matched_vendor.get("ruc") else ""
        st.success(f"Proveedor: **{matched_vendor['name']}**{ruc_txt}")
        vendor_name = matched_vendor["name"]
        doc_type = matched_vendor["doc_type"]
        term_days = matched_vendor["term_days"]
        if doc_type == "credito":
            st.info(f"Este proveedor trabaja a **crédito, {term_days} días**.")
        else:
            st.info("Este proveedor trabaja al **contado**.")
    else:
        st.warning("No se encontró ningún proveedor con esos datos. Regístralo como nuevo proveedor:")
        is_new_vendor = True
        colA, colB = st.columns(2)
        with colA:
            vendor_name = st.text_input(
                "Nombre del proveedor",
                value=("" if q.isdigit() else query),
                key="nf_new_vendor_name",
            )
        with colB:
            new_vendor_ruc = st.text_input(
                "RUC (opcional)",
                value=(q if q.isdigit() else ""),
                key="nf_new_vendor_ruc",
                max_chars=11,
            )
        st.caption(
            "Se guarda al contado por defecto — el administrador puede reclasificarlo "
            "luego en Configuración si trabaja a crédito."
        )
        doc_type, term_days = "contado", None
else:
    st.caption("Escribe el RUC o el nombre del proveedor para buscarlo. Si no existe, podrás crearlo aquí mismo.")

col1, col2 = st.columns(2)
with col1:
    document_type = st.selectbox("Tipo de documento", DOCUMENT_TYPES, key="nf_doc_type_sel")
    invoice_number = st.text_input("N° de documento", placeholder="F001-00123", key="nf_invoice_number")
    amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f", key="nf_amount")
with col2:
    issue_date = st.date_input("Fecha de emisión", value=None, key="nf_issue_date")
    notes = st.text_area("Notas (opcional)", height=68, key="nf_notes")

if st.button("Registrar factura", type="primary"):
    if not vendor_name or not vendor_name.strip() or not invoice_number.strip() or amount <= 0 or not issue_date:
        st.error("Completa proveedor, N° de documento, monto y fecha de emisión.")
    else:
        vendor_name = vendor_name.strip()
        can_submit = True

        if is_new_vendor:
            all_current_vendors = db.get_vendors()
            name_l = vendor_name.lower()
            ruc_clean = new_vendor_ruc.strip() or None

            name_match = next((v for v in all_current_vendors if v["name"].strip().lower() == name_l), None)
            ruc_match = (
                next((v for v in all_current_vendors if (v.get("ruc") or "") == ruc_clean), None)
                if ruc_clean else None
            )

            if name_match:
                # Ya existe un proveedor con ese nombre — se usa su configuración
                # en vez de crear un duplicado.
                vendor_name = name_match["name"]
                doc_type = name_match["doc_type"]
                term_days = name_match["term_days"]
            elif ruc_match:
                st.error(f"El RUC {ruc_clean} ya pertenece a **{ruc_match['name']}**. Búscalo por ese nombre o RUC arriba.")
                can_submit = False
            else:
                try:
                    db.create_vendor({
                        "name": vendor_name,
                        "ruc": ruc_clean,
                        "doc_type": "contado",
                        "term_days": None,
                    })
                except Exception:
                    st.error("No se pudo registrar el proveedor: el nombre o el RUC ya está en uso.")
                    can_submit = False

        if can_submit:
            issue_date_str = issue_date.isoformat()
            due_date_str = (
                utils.add_days(issue_date_str, term_days)
                if doc_type == "credito" and term_days
                else issue_date_str
            )
            db.create_invoice({
                "branch": branch,
                "vendor": vendor_name,
                "invoice_number": invoice_number.strip(),
                "document_type": document_type,
                "doc_type": doc_type,
                "amount": amount,
                "issue_date": issue_date_str,
                "term_days": term_days,
                "due_date": due_date_str,
                "status": "pendiente",
                "notes": notes.strip(),
            })
            tipo_txt = "contado" if doc_type == "contado" else f"crédito a {term_days} días"
            st.success(f"{document_type} registrado ({vendor_name} · {tipo_txt}). Vence el {utils.fmt_short(due_date_str)}.")
            for k in ["nf_query", "nf_new_vendor_name", "nf_new_vendor_ruc", "nf_invoice_number", "nf_amount", "nf_notes"]:
                st.session_state.pop(k, None)
            st.rerun()
