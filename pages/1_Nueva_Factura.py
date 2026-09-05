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
ruc = st.text_input("RUC del proveedor", key="nf_ruc", max_chars=11, placeholder="20123456789")

matched_vendor = db.get_vendor_by_ruc(ruc) if ruc.strip() else None
vendor_name = None
doc_type = None
term_days = None

if matched_vendor:
    st.success(f"Proveedor encontrado: **{matched_vendor['name']}**")
    vendor_name = matched_vendor["name"]
    doc_type = matched_vendor["doc_type"]
    term_days = matched_vendor["term_days"]
    if doc_type == "credito":
        st.info(f"Este proveedor trabaja a **crédito, {term_days} días**.")
    else:
        st.info("Este proveedor trabaja al **contado**.")
elif ruc.strip():
    st.warning(
        "No se encontró ningún proveedor con ese RUC. Complétalo como proveedor nuevo "
        "(se guarda al contado por defecto — el administrador puede reclasificarlo luego en Configuración)."
    )
    vendor_name = st.text_input("Nombre del proveedor nuevo", key="nf_new_vendor_name")
    doc_type, term_days = "contado", None
else:
    st.caption("Escribe el RUC del proveedor para buscarlo.")

col1, col2 = st.columns(2)
with col1:
    document_type = st.selectbox("Tipo de documento", DOCUMENT_TYPES, key="nf_doc_type_sel")
    invoice_number = st.text_input("N° de documento", placeholder="F001-00123", key="nf_invoice_number")
    amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f", key="nf_amount")
with col2:
    issue_date = st.date_input("Fecha de emisión", value=None, key="nf_issue_date")
    notes = st.text_area("Notas (opcional)", height=68, key="nf_notes")

if st.button("Registrar factura", type="primary"):
    if not ruc.strip() or not vendor_name or not vendor_name.strip() or not invoice_number.strip() or amount <= 0 or not issue_date:
        st.error("Completa RUC, proveedor, N° de documento, monto y fecha de emisión.")
    else:
        if not matched_vendor:
            db.save_vendor({"name": vendor_name.strip(), "ruc": ruc.strip(), "doc_type": "contado", "term_days": None})

        issue_date_str = issue_date.isoformat()
        due_date_str = (
            utils.add_days(issue_date_str, term_days)
            if doc_type == "credito" and term_days
            else issue_date_str
        )
        db.create_invoice({
            "branch": branch,
            "vendor": vendor_name.strip(),
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
        for k in ["nf_ruc", "nf_new_vendor_name", "nf_invoice_number", "nf_amount", "nf_notes"]:
            st.session_state.pop(k, None)
        st.rerun()
