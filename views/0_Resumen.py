import streamlit as st
import db
import utils

invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
settings = db.get_settings()
track_contado = settings.get("track_contado", True)
events = utils.get_payment_events(
    invoices, letras, canje_facturas, track_contado,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
    letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
)
stats = utils.compute_stats(events)

st.title("🗓️ Control Compras")
st.caption("Consolidado de facturas y letras · 6 sucursales")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vencido", utils.money(stats["vencido"]))
c2.metric("Vence hoy", utils.money(stats["hoy"]))
c3.metric("Vence esta semana", utils.money(stats["esta_semana"]))
c4.metric("Total pendiente", utils.money(stats["total_pendiente"]))

st.divider()
st.subheader("Próximos vencimientos")

FILTROS_TIPO = ["Todos", "Contado", "Crédito", "Letras"]


def _matches_filtro(e, filtro):
    if filtro == "Todos":
        return True
    if filtro == "Contado":
        return e["kind"] == "invoice" and e["label"] == "Contado"
    if filtro == "Crédito":
        return e["kind"] == "invoice" and e["label"] != "Contado"
    if filtro == "Letras":
        return e["kind"] == "letra"
    return True


MOSTRAR_TOPE = 20


def _render_lista(items, destino):
    for e in items[:MOSTRAR_TOPE]:
        _render_row(e)
    restantes = len(items) - MOSTRAR_TOPE
    if restantes > 0:
        st.caption(f"+ {restantes} más — ve a **{destino}** para verlas todas.")


def _render_row(e):
    cols = st.columns([3, 2, 2, 1.5, 1.5])
    cols[0].markdown(f"**{e['vendor']}**  \n<span style='font-size:12px;color:gray'>Fact. {e['invoice_number']} · {e['branch']}</span>", unsafe_allow_html=True)
    cols[1].write(e["label"])
    badge = f"🔴 Vencido {utils.fmt_short(e['date'])}" if e["overdue"] else f"🟡 {utils.fmt_short(e['date'])}"
    cols[2].write(badge)
    cols[3].write(f"**{utils.money(e['amount'])}**")
    with cols[4]:
        if st.button("Pagado", key=f"pay_{e['kind']}_{e['ref_id']}"):
            st.session_state["_pay_target"] = e
            st.session_state["_show_pay_dialog"] = True
            st.rerun()


if not events:
    st.info("No hay pagos pendientes registrados. Ve a **Nueva Factura** en el menú de la izquierda para empezar.")
else:
    filtro = st.radio("Filtrar", FILTROS_TIPO, horizontal=True, label_visibility="collapsed", key="resumen_filtro_tipo")

    if filtro == "Todos":
        # Agrupado por tipo (en vez de una sola lista mezclada por fecha) —
        # así no se confunden facturas sueltas con letras ya agrupadas.
        grupos = [
            ("📄 Facturas a crédito", "Crédito", "Facturas"),
            ("💵 Contado", "Contado", "Facturas"),
            ("🔁 Letras", "Letras", "Letras → Todas las letras"),
        ]
        hubo_algo = False
        for titulo, tipo, destino in grupos:
            items = [e for e in events if _matches_filtro(e, tipo)]
            if not items:
                continue
            hubo_algo = True
            subtotal = utils.dsum(i["amount"] for i in items)
            st.markdown(f"**{titulo}** · {len(items)} · {utils.money(subtotal)}")
            _render_lista(items, destino)
            st.divider()
        if not hubo_algo:
            st.caption("No hay ninguno con este filtro.")
    else:
        filtered = [e for e in events if _matches_filtro(e, filtro)]
        if not filtered:
            st.caption("No hay ninguno con este filtro.")
        destino = "Letras → Todas las letras" if filtro == "Letras" else "Facturas"
        _render_lista(filtered, destino)

if st.session_state.get("_show_pay_dialog"):
    e = st.session_state["_pay_target"]

    def _cerrar_pay_dialog():
        st.session_state["_show_pay_dialog"] = False

    @st.dialog("Marcar como pagado", on_dismiss=_cerrar_pay_dialog)
    def _pay_dialog():
        st.write(f"**{e['vendor']}** · Fact. {e['invoice_number']} · {e['label']} · {utils.money(e['amount'])}")
        fecha = st.date_input("Fecha de pago", value=None)
        col_a, col_b = st.columns(2)
        if col_a.button("Cancelar"):
            st.session_state["_show_pay_dialog"] = False
            st.rerun()
        if col_b.button("Confirmar pago", type="primary"):
            fecha_str = (fecha or __import__("datetime").date.today()).isoformat()
            actor = utils.current_actor()
            if e["kind"] == "letra":
                db.mark_letra_paid(e["ref_id"], fecha_str, paid_by=actor)
            else:
                db.mark_invoice_paid(e["ref_id"], fecha_str, paid_by=actor)
            st.session_state["_show_pay_dialog"] = False
            st.rerun()

    _pay_dialog()
