import streamlit as st
import pandas as pd
import db
import utils

st.set_page_config(page_title="Consolidado", page_icon="📋", layout="wide")
utils.check_password()

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
    df_view = df[["issue_date", "branch", "vendor", "invoice_number", "doc_type", "amount", "due_date", "status"]].copy()
    df_view.columns = ["Emisión", "Sucursal", "Proveedor", "N° Factura", "Tipo", "Monto (S/)", "Vence", "Estado"]
    df_view["Vencida"] = [
        (r["status"] != "pagada" and r["due_date"] < today) for r in rows
    ]
    st.dataframe(
        df_view.drop(columns=["Vencida"]).style.apply(
            lambda s: ["background-color: #f8e6e6" if v else "" for v in df_view["Vencida"]], axis=0
        ),
        use_container_width=True, hide_index=True,
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
            st.switch_page("pages/3_Canjear_a_Letras.py")

    st.divider()
    st.subheader("Marcar pago directo o eliminar")
    for r in rows:
        cols = st.columns([3, 1.5, 1.3, 1.3])
        cols[0].write(f"**{r['vendor']}** · Fact. {r['invoice_number']} · {r['branch']} · {utils.money(r['amount'])}")
        if r["status"] == "pendiente":
            if cols[1].button("Marcar pagada", key=f"pay_{r['id']}"):
                st.session_state["_direct_pay_id"] = r["id"]
                st.rerun()
        else:
            cols[1].write(f"Estado: {r['status']}")
        if cols[2].button("Eliminar", key=f"del_{r['id']}"):
            st.session_state["_confirm_delete_id"] = r["id"]
            st.rerun()

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
            db.mark_invoice_paid(inv_id, fecha_str)
            st.session_state["_direct_pay_id"] = None
            st.rerun()

    _direct_pay_dialog()

if st.session_state.get("_confirm_delete_id"):
    inv_id = st.session_state["_confirm_delete_id"]

    @st.dialog("Confirmar eliminación")
    def _confirm_delete_dialog():
        st.write("Esta acción eliminará la factura de forma permanente.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar"):
            st.session_state["_confirm_delete_id"] = None
            st.rerun()
        if c2.button("Eliminar", type="primary"):
            db.delete_invoice(inv_id)
            st.session_state["_confirm_delete_id"] = None
            st.rerun()

    _confirm_delete_dialog()
