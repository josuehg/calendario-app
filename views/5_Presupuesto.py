import plotly.graph_objects as go
import streamlit as st
import db
import utils

st.title("📊 Presupuesto")
st.caption("En qué semana futura pega cada factura, letra o gasto (fijo y variable) pendiente.")

HORIZON_OPTIONS = [4, 13, 26]
horizon = st.radio(
    "Horizonte", HORIZON_OPTIONS, index=1, horizontal=True, key="pp_horizon",
    format_func=lambda w: f"{w} semanas",
)

db.ensure_expense_instances()
invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
expenses = db.list_expenses()
incomes = db.list_incomes()
settings = db.get_settings()
track_contado = settings.get("track_contado", True)
events = utils.get_payment_events(
    invoices, letras, canje_facturas, track_contado, expenses,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
    letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
)
buckets = utils.weekly_buckets(events, weeks_ahead=horizon)
today = utils.today_str()

# ---------- saldo de caja / disponible para comprometer ----------
if not settings.get("caja_saldo_inicial_fecha"):
    st.info(
        "Configura el saldo inicial de caja en **Configuración** para ver aquí "
        "cuánto tienes disponible para comprometer en un pedido nuevo, y el "
        "simulador por plazo de proveedor de más abajo."
    )
else:
    caja = utils.compute_cash_balance(
        invoices, letras, expenses, incomes,
        saldo_inicial=settings.get("caja_saldo_inicial") or 0.0,
        saldo_inicial_fecha=settings.get("caja_saldo_inicial_fecha"),
    )
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Saldo de caja actual", utils.money(caja["saldo_actual"]))
    cc2.metric("Comprometido (pendiente)", utils.money(caja["comprometido"]))
    cc3.metric("💰 Disponible para comprometer", utils.money(caja["disponible"]))
    if caja["disponible"] < 0:
        st.error("Ya tienes más comprometido que lo que hay en caja — cuidado con hacer un pedido nuevo.")
    st.divider()

    # ---------- simulador: cuánto comprometer con un proveedor a X días ----------
    st.subheader("🧮 ¿Cuánto puedo comprometer con un proveedor nuevo?")
    st.caption(
        "Revisa semana por semana desde hoy hasta la fecha en que vencería "
        "esa compra (según el plazo del proveedor) — tu saldo actual, más lo "
        "que esperas vender hasta cada semana, menos TODO lo que ya está "
        "comprometido hasta ahí. Usa la semana más ajustada del camino, no "
        "solo el día final: si algo grande cae antes, ese es tu verdadero límite."
    )
    plazo_sim = st.radio(
        "Plazo del proveedor", utils.TERM_OPTIONS, index=2, horizontal=True, key="pp_sim_plazo",
        format_func=lambda d: f"{d} días",
    )
    venta_diaria_sim = utils.average_daily_income(incomes, days_back=30)
    sim = utils.max_new_purchase(events, caja["saldo_actual"], venta_diaria_sim, plazo_sim, today)
    st.metric(
        f"Máximo recomendado a {plazo_sim} días (vencería el {utils.fmt_short(sim['fecha_vence'])})",
        utils.money(sim["maximo"]),
    )
    if sim["semana_mas_ajustada"] != sim["fecha_vence"]:
        st.caption(
            f"📍 Limitado por la semana del {utils.fmt_short(sim['semana_mas_ajustada'])}, "
            "no por el día final — ahí es donde más ajustada se pone la caja en el camino."
        )
    if venta_diaria_sim == 0:
        st.caption("Sin ingresos registrados, esto no suma venta proyectada — registra en **Ingresos** para un número más real.")
    if sim["proyectado"] <= 0:
        st.error(
            f"Con un plazo de {plazo_sim} días ya proyectas caja en rojo para la semana del "
            f"{utils.fmt_short(sim['semana_mas_ajustada'])} — no es recomendable comprometer nada nuevo a ese plazo."
        )
    st.divider()

# ---------- límite de compra (fuera de los gastos fijos) ----------
st.subheader("🛒 Límite de compra (fuera de gastos fijos)")
st.caption(
    "Cuánto puedes comprometer en compras NUEVAS a proveedores sin afectar "
    "tus gastos fijos operativos (alquiler, planilla, servicios, etc.), según "
    "tu promedio de ventas reciente. No incluye facturas/letras a "
    "proveedores — eso es justo lo que este límite busca acotar."
)
DAYS_BACK_OPTIONS = [7, 30, 90]
dias_venta = st.radio(
    "Promedio de ventas de los últimos...", DAYS_BACK_OPTIONS, index=1, horizontal=True, key="pp_dias_venta",
    format_func=lambda d: f"{d} días",
)
fixed_active = db.list_fixed_expenses(active_only=True)
limite = utils.purchase_limit(incomes, fixed_active, days_back=dias_venta)
if limite["venta_diaria"] == 0:
    st.caption(
        "No hay ingresos registrados en ese rango — registra tus ventas en "
        "**Ingresos** (o con /ingreso desde Telegram) para ver esto."
    )
else:
    lc1, lc2, lc3 = st.columns(3)
    lc1.metric("Venta promedio semanal", utils.money(limite["venta_semanal"]))
    lc2.metric("Gastos fijos semanales", utils.money(limite["gastos_fijos_semanales"]))
    lc3.metric("🛒 Límite de compra semanal", utils.money(limite["limite_semanal"]))
    lc4, lc5, lc6 = st.columns(3)
    lc4.metric("Venta promedio mensual", utils.money(limite["venta_mensual"]))
    lc5.metric("Gastos fijos mensuales", utils.money(limite["gastos_fijos_mensuales"]))
    lc6.metric("🛒 Límite de compra mensual", utils.money(limite["limite_mensual"]))
    if limite["limite_semanal"] < 0:
        st.error("Tus gastos fijos ya superan tu venta promedio — no hay margen para compras nuevas sin tocar la caja.")
st.divider()

labels = [f"{utils.fmt_short(b['start'])}" for b in buckets]
amounts = [b["amount"] for b in buckets]
colors = ["#08444d" if (b["start"] <= today <= b["end"]) else "#0b5d68" for b in buckets]

fig = go.Figure(go.Bar(
    x=labels, y=amounts, marker_color=colors,
    text=[utils.money(a) if a > 0 else "" for a in amounts],
    textposition="outside",
))
fig.update_layout(
    height=380, margin=dict(t=20, b=20, l=20, r=20),
    yaxis_title="Monto (S/)", xaxis_title=f"Semana (inicio) — próximas {horizon} semanas",
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, width="stretch")

st.divider()
for b in buckets:
    is_current = b["start"] <= today <= b["end"]
    cols = st.columns([3, 1, 1])
    tag = " 🟢 esta semana" if is_current else ""
    cols[0].write(f"**{utils.fmt_short(b['start'])} – {utils.fmt_short(b['end'])}**{tag}")
    cols[1].write(f"{b['count']} pago(s)")
    cols[2].write(f"**{utils.money(b['amount'])}**")

st.divider()
st.subheader("Balance semanal (histórico)")
st.caption(
    "Por semana: lo que vencía (Debido), lo que realmente se pagó (Pagado) y "
    "el saldo pendiente acumulado hasta esa semana — igual que llevarías la "
    "cuenta en una hoja de cálculo, pero calculado solo con tus datos."
)
WEEKS_BACK_OPTIONS = [4, 8, 12]
weeks_back = st.radio(
    "Semanas hacia atrás", WEEKS_BACK_OPTIONS, index=1, horizontal=True, key="pp_weeks_back",
    format_func=lambda w: f"{w} semanas",
)
balance = utils.weekly_balance(
    invoices, letras, expenses, weeks_back=weeks_back,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
)
if not balance:
    st.caption("No hay movimientos registrados todavía.")
else:
    bc1, bc2, bc3, bc4 = st.columns([2.5, 1, 1, 1])
    bc1.markdown("**Semana**")
    bc2.markdown("**Debido**")
    bc3.markdown("**Pagado**")
    bc4.markdown("**Saldo pendiente**")
    for b in balance:
        bc1, bc2, bc3, bc4 = st.columns([2.5, 1, 1, 1])
        is_current = b["start"] <= today <= b["end"]
        tag = " 🟢" if is_current else ""
        bc1.write(f"{utils.fmt_short(b['start'])} – {utils.fmt_short(b['end'])}{tag}")
        bc2.write(utils.money(b["debido"]))
        bc3.write(utils.money(b["pagado"]))
        color = ":red" if b["saldo"] > 0 else ":green"
        bc4.markdown(f"{color}[**{utils.money(b['saldo'])}**]")
