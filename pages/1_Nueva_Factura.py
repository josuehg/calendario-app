import streamlit as st
import db
import utils

st.set_page_config(page_title="Nueva Factura", page_icon="🧾", layout="wide")
utils.check_password()

st.title("🧾 Registrar factura")

branches = db.get_branches() + ["Oficina central"]
vendors = sorted(set(i["vendor"] for i in db.list_invoices())) if db.list_invoices() else []

with st.form("nueva_factura", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        branch = st.selectbox("Sucursal", branches)
        vendor = st.text_input("Proveedor", placeholder="Ej. Distribuidora Continental")
        invoice_number = st.text_input("N° de factura", placeholder="F001-00123")
        amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f")
    with col2:
        doc_type = st.radio("Tipo de pago", ["contado", "credito"], format_func=lambda x: "Contado" if x == "contado" else "Crédito", horizontal=True)
        issue_date = st.date_input("Fecha de emisión", value=None)
        term_days = None
        if doc_type == "credito":
            term_days = st.selectbox("Plazo", utils.TERM_OPTIONS, format_func=lambda d: f"{d} días")
        notes = st.text_area("Notas (opcional)", height=68)

    submitted = st.form_submit_button("Registrar factura", type="primary")

    if submitted:
        if not vendor.strip() or not invoice_number.strip() or amount <= 0 or not issue_date:
            st.error("Completa proveedor, N° de factura, monto y fecha de emisión.")
        else:
            issue_date_str = issue_date.isoformat()
            due_date_str = utils.add_days(issue_date_str, term_days) if doc_type == "credito" else issue_date_str
            db.create_invoice({
                "branch": branch,
                "vendor": vendor.strip(),
                "invoice_number": invoice_number.strip(),
                "doc_type": doc_type,
                "amount": amount,
                "issue_date": issue_date_str,
                "term_days": term_days,
                "due_date": due_date_str,
                "status": "pendiente",
                "notes": notes.strip(),
            })
            st.success(f"Factura registrada. Vence el {utils.fmt_short(due_date_str)}.")
