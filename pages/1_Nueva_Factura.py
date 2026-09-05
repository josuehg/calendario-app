import streamlit as st
import db
import utils

st.title("🧾 Registrar factura")

auth_role = st.session_state.get("auth_role")
auth_branch = st.session_state.get("auth_branch")

vendors = db.get_vendors()
vendor_names = [v["name"] for v in vendors]
vendor_by_name = {v["name"]: v for v in vendors}

if not vendors:
    st.warning(
        "Aún no hay proveedores configurados. Si eres administrador, agrégalos en "
        "**Configuración** con su tipo (contado/crédito) y plazo. Mientras tanto, puedes "
        "registrar con un proveedor nuevo — se guardará como contado por defecto."
    )

with st.form("nueva_factura", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
        if auth_role == "branch":
            st.text_input("Sucursal", value=auth_branch, disabled=True)
            branch = auth_branch
        else:
            branch = st.selectbox("Sucursal", db.get_branches() + ["Oficina central"])

        vendor_options = vendor_names + ["+ Proveedor nuevo"]
        vendor_choice = st.selectbox("Proveedor", vendor_options)
        new_vendor_name = ""
        if vendor_choice == "+ Proveedor nuevo":
            new_vendor_name = st.text_input("Nombre del proveedor nuevo")

        invoice_number = st.text_input("N° de factura", placeholder="F001-00123")
        amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f")

    with col2:
        issue_date = st.date_input("Fecha de emisión", value=None)

        if vendor_choice in vendor_by_name:
            v = vendor_by_name[vendor_choice]
            if v["doc_type"] == "credito":
                st.info(f"Este proveedor trabaja a **crédito, {v['term_days']} días** (configurado por el administrador).")
            else:
                st.info("Este proveedor trabaja al **contado**.")
        else:
            st.info("Proveedor nuevo → se registrará como **contado** por defecto. El administrador puede reclasificarlo en Configuración.")

        notes = st.text_area("Notas (opcional)", height=68)

    submitted = st.form_submit_button("Registrar factura", type="primary")

    if submitted:
        vendor_name = new_vendor_name.strip() if vendor_choice == "+ Proveedor nuevo" else vendor_choice
        if not vendor_name or not invoice_number.strip() or amount <= 0 or not issue_date:
            st.error("Completa proveedor, N° de factura, monto y fecha de emisión.")
        else:
            if vendor_choice == "+ Proveedor nuevo":
                doc_type, term_days = "contado", None
                db.save_vendor({"name": vendor_name, "doc_type": "contado", "term_days": None})
            else:
                v = vendor_by_name[vendor_choice]
                doc_type, term_days = v["doc_type"], v["term_days"]

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
                "doc_type": doc_type,
                "amount": amount,
                "issue_date": issue_date_str,
                "term_days": term_days,
                "due_date": due_date_str,
                "status": "pendiente",
                "notes": notes.strip(),
            })
            tipo_txt = "contado" if doc_type == "contado" else f"crédito a {term_days} días"
            st.success(f"Factura registrada ({vendor_name} · {tipo_txt}). Vence el {utils.fmt_short(due_date_str)}.")
