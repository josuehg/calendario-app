import streamlit as st
import pandas as pd
import db
import utils

st.title("📋 Consolidado de facturas")

invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
today = utils.today_str()

# ---------- filtros ----------
branches = ["Todas"] + db.get_branches() + ["Oficina central"]
f1, f2, f3, f4, f5 = st.columns([1.2, 1.4, 1, 1, 1])
f_branch = f1.selectbox("Sucursal", branches)
f_vendor = f2.text_input("Buscar proveedor")
f_status = f3.selectbox("Estado", ["Todos", "pendiente", "canjeada", "pagada"])
f_from = f4.date_input("Desde", value=None)
f_to = f5.date_input("Hasta", value=None)

rows = invoices
if f_branch != "Todas":
    rows = [r for r in rows if r["branch"] == f_branch]
if f_vendor:
    rows = [r for r in rows if f_vendor.lower() in r["vendor"].lower()]
if f_status != "Todos":
    rows = [r for r in rows if r["status"] == f_status]
if f_from:
    rows = [r for r in rows if r["issue_date"] >= f_from.isoformat()]
if f_to:
    rows = [r for r in rows if r["issue_date"] <= f_to.isoformat()]

if not rows:
    st.info("No hay facturas con estos filtros.")
else:
    df = pd.DataFrame(rows)
    for col, default in [("document_type", "Factura"), ("registered_by", "—")]:
        if col not in df.columns:
            df[col] = default
    df["registered_by"] = df["registered_by"].fillna("—")
    df_view = df[["issue_date", "branch", "vendor", "document_type", "invoice_number", "doc_type", "amount", "due_date", "status", "registered_by"]].copy()
    df_view.columns = ["Emisión", "Sucursal", "Proveedor", "Tipo Doc.", "N° Documento", "Tipo", "Monto (S/)", "Vence", "Estado", "Registrado por"]
    df_view["Vencida"] = [
        (r["status"] != "pagada" and r["due_date"] < today) for r in rows
    ]
    st.dataframe(
        df_view.drop(columns=["Vencida"]).style.apply(
            lambda s: ["background-color: #f8e6e6" if v else "" for v in df_view["Vencida"]], axis=0
        ),
        width="stretch", hide_index=True,
    )

    st.divider()
    st.subheader("Seleccionar facturas a crédito pendientes para canjear")
    pendientes_credito = [r for r in rows if r["status"] == "pendiente" and r["doc_type"] == "credito"]
    if not pendientes_credito:
        st.caption("No hay facturas a crédito pendientes de canje con estos filtros.")
    else:
        options = {
            f"{r['vendor']} · Fact. {r['invoice_number']} · {utils.money(r['amount'])} · vence {utils.fmt_short(r['due_date'])}": r["id"]
            for r in pendientes_credito
        }
        selected_labels = st.multiselect("Facturas pendientes (a crédito)", list(options.keys()))
        selected_ids = [options[l] for l in selected_labels]
        if st.button("Canjear seleccionadas a letras →", type="primary", disabled=not selected_ids):
            st.session_state["canje_preselect"] = selected_ids
            st.switch_page("views/3_Canjear_a_Letras.py")

    st.divider()
    st.subheader("Editar, pagar o eliminar")
    for r in rows:
        cols = st.columns([3, 1.2, 1.2, 1.2])
        cols[0].write(f"**{r['vendor']}** · Fact. {r['invoice_number']} · {r['branch']} · {utils.money(r['amount'])}")
        meta = f"Estado: {r['status']} · registró: {r.get('registered_by') or '—'}"
        if r["status"] == "pagada" and r.get("paid_by"):
            meta += f" · pagó: {r['paid_by']}" + (f" ({utils.fmt_short(r['paid_at'])})" if r.get("paid_at") else "")
        cols[0].caption(meta)
        if cols[1].button("Editar", key=f"edit_{r['id']}", width="stretch"):
            st.session_state["_edit_inv"] = r
            st.rerun()
        if r["status"] == "pendiente":
            if cols[2].button("Pagar", key=f"pay_{r['id']}", width="stretch"):
                st.session_state["_direct_pay_id"] = r["id"]
                st.rerun()
        if cols[3].button("Eliminar", key=f"del_{r['id']}", width="stretch"):
            st.session_state["_confirm_delete_id"] = r["id"]
            st.rerun()

if st.session_state.get("_edit_inv"):
    inv = st.session_state["_edit_inv"]

    @st.dialog("Editar factura")
    def _edit_inv_dialog():
        if inv["status"] != "pendiente":
            st.warning(
                f"Esta factura está **{inv['status']}**. Cambiar el monto no ajusta la(s) "
                "letra(s) del canje ni el pago ya registrado — hazlo solo para corregir datos."
            )
        c1, c2 = st.columns(2)
        vendor = c1.text_input("Proveedor", value=inv["vendor"], key="ei_vendor")
        number = c2.text_input("N° de documento", value=inv["invoice_number"], key="ei_number")
        DT = ["Factura", "Boleta", "Nota de compra", "Otro"]
        dt = c1.selectbox("Tipo de documento", DT,
                          index=DT.index(inv.get("document_type", "Factura")) if inv.get("document_type", "Factura") in DT else 0,
                          key="ei_dt")
        amount = c2.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
                                 value=float(inv["amount"]), key="ei_amount")
        c3, c4 = st.columns(2)
        issue = c3.date_input("Fecha de emisión",
                              value=__import__("datetime").date.fromisoformat(inv["issue_date"]) if inv.get("issue_date") else None,
                              key="ei_issue")
        doc_type = c4.radio("Condición", ["contado", "credito"],
                            index=1 if inv["doc_type"] == "credito" else 0,
                            format_func=lambda x: "Contado" if x == "contado" else "Crédito",
                            horizontal=True, key="ei_doctype")
        term_days = inv.get("term_days")
        if doc_type == "credito":
            term_days = c3.selectbox("Plazo (días)", utils.TERM_OPTIONS,
                                     index=utils.TERM_OPTIONS.index(inv["term_days"]) if inv.get("term_days") in utils.TERM_OPTIONS else 0,
                                     key="ei_term")
        due = c4.date_input("Vencimiento",
                            value=__import__("datetime").date.fromisoformat(inv["due_date"]) if inv.get("due_date") else None,
                            key="ei_due")
        notes = st.text_input("Notas", value=inv.get("notes") or "", key="ei_notes")

        b1, b2 = st.columns(2)
        if b1.button("Guardar", type="primary", width="stretch"):
            if not vendor.strip() or not number.strip() or amount <= 0 or not issue or not due:
                st.error("Completa proveedor, N° de documento, monto, emisión y vencimiento.")
            else:
                db.update_invoice(inv["id"], {
                    "vendor": vendor.strip(),
                    "invoice_number": number.strip(),
                    "document_type": dt,
                    "amount": utils.round2(amount),
                    "issue_date": issue.isoformat(),
                    "doc_type": doc_type,
                    "term_days": term_days if doc_type == "credito" else None,
                    "due_date": due.isoformat(),
                    "notes": notes.strip() or None,
                })
                st.session_state["_edit_inv"] = None
                st.rerun()
        if b2.button("Cancelar", width="stretch"):
            st.session_state["_edit_inv"] = None
            st.rerun()

    _edit_inv_dialog()

if st.session_state.get("_direct_pay_id"):
    inv_id = st.session_state["_direct_pay_id"]

    @st.dialog("Marcar como pagada")
    def _direct_pay_dialog():
        fecha = st.date_input("Fecha de pago", value=None)
        c1, c2 = st.columns(2)
        if c1.button("Cancelar"):
            st.session_state["_direct_pay_id"] = None
            st.rerun()
        if c2.button("Confirmar", type="primary"):
            fecha_str = (fecha or __import__("datetime").date.today()).isoformat()
            db.mark_invoice_paid(inv_id, fecha_str, paid_by=utils.current_actor())
            st.session_state["_direct_pay_id"] = None
            st.rerun()

    _direct_pay_dialog()

if st.session_state.get("_confirm_delete_id"):
    inv_id = st.session_state["_confirm_delete_id"]

    _inv_del = next((x for x in invoices if x["id"] == inv_id), None)

    @st.dialog("Confirmar eliminación")
    def _confirm_delete_dialog():
        st.write("Esta acción eliminará la factura de forma permanente.")
        if _inv_del and _inv_del["status"] == "canjeada":
            st.warning("Está **canjeada**: su(s) letra(s) del canje seguirán existiendo. "
                       "Si querías deshacer el canje, borra también esas letras en la página Letras.")
        elif _inv_del and _inv_del["status"] == "pagada":
            st.warning("Está marcada como **pagada**.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar"):
            st.session_state["_confirm_delete_id"] = None
            st.rerun()
        if c2.button("Eliminar", type="primary"):
            db.delete_invoice(inv_id)
            st.session_state["_confirm_delete_id"] = None
            st.rerun()

    _confirm_delete_dialog()
