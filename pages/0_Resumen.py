import streamlit as st
import db
import utils

invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
events = utils.get_payment_events(invoices, letras, canje_facturas)
stats = utils.compute_stats(events)

st.title("🗓️ Calendario Maestro de Pagos")
st.caption("Consolidado de facturas y letras · 6 sucursales")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vencido", utils.money(stats["vencido"]))
c2.metric("Vence hoy", utils.money(stats["hoy"]))
c3.metric("Vence esta semana", utils.money(stats["esta_semana"]))
c4.metric("Total pendiente", utils.money(stats["total_pendiente"]))

st.divider()
st.subheader("Próximos vencimientos")

if not events:
    st.info("No hay pagos pendientes registrados. Ve a **Nueva Factura** en el menú de la izquierda para empezar.")
else:
    for e in events[:15]:
        cols = st.columns([3, 2, 2, 1.5, 1.5])
        cols[0].markdown(f"**{e['vendor']}**  \n<span style='font-size:12px;color:gray'>Fact. {e['invoice_number']} · {e['branch']}</span>", unsafe_allow_html=True)
        cols[1].write(e["label"])
        badge = "🔴 Vencido" if e["overdue"] else f"🟡 {utils.fmt_short(e['date'])}"
        cols[2].write(badge)
        cols[3].write(f"**{utils.money(e['amount'])}**")
        with cols[4]:
            if st.button("Pagado", key=f"pay_{e['kind']}_{e['ref_id']}"):
                st.session_state["_pay_target"] = e
                st.session_state["_show_pay_dialog"] = True
                st.rerun()

if st.session_state.get("_show_pay_dialog"):
    e = st.session_state["_pay_target"]

    @st.dialog("Marcar como pagado")
    def _pay_dialog():
        st.write(f"**{e['vendor']}** · Fact. {e['invoice_number']} · {e['label']} · {utils.money(e['amount'])}")
        fecha = st.date_input("Fecha de pago", value=None)
        col_a, col_b = st.columns(2)
        if col_a.button("Cancelar"):
            st.session_state["_show_pay_dialog"] = False
            st.rerun()
        if col_b.button("Confirmar pago", type="primary"):
            fecha_str = (fecha or __import__("datetime").date.today()).isoformat()
            if e["kind"] == "letra":
                db.mark_letra_paid(e["ref_id"], fecha_str)
            else:
                db.mark_invoice_paid(e["ref_id"], fecha_str)
            st.session_state["_show_pay_dialog"] = False
            st.rerun()

    _pay_dialog()
