import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
import utils

st.title("🧮 Simulador de crédito")
st.caption(
    "¿Qué pasa con tu caja si usas un crédito para cancelar deudas caras? Mueve "
    "cuánto le cancelas a cada una y mira la caja a fin de cada mes. Todo sale de "
    "tus datos: Deudas (las informales), lo pendiente del Calendario, tus ventas "
    "registradas y los ingresos fijos. Nada se guarda: es solo para comparar."
)

db.ensure_expense_instances()
invoices = db.list_invoices()
letras = db.list_letras()
expenses = db.list_expenses()
incomes = db.list_incomes()
settings = db.get_settings()
fixed_expenses = db.list_fixed_expenses()
fixed_receipts = db.list_fixed_income_receipts()
events = utils.get_payment_events(
    invoices, letras, db.list_canje_facturas(), settings.get("track_contado", True), expenses,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
    letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
)
ingresos_esperados = utils.fixed_income_expected(db.list_fixed_incomes(), fixed_receipts, months_ahead=8)
deudas = utils.simulator_debts(db.list_debts(active_only=True), fixed_expenses)
today = utils.today_str()

if not deudas:
    st.info(
        "No hay deudas informales registradas con saldo. Regístralas en **Deudas** "
        "(capital, saldo y cuota) para simular cuánto te conviene cancelar."
    )
    st.stop()

# ---------- supuestos ----------
caja_app = None
if settings.get("caja_saldo_inicial_fecha"):
    caja_app = utils.compute_cash_balance(
        invoices, letras, expenses, incomes,
        saldo_inicial=settings.get("caja_saldo_inicial") or 0.0,
        saldo_inicial_fecha=settings.get("caja_saldo_inicial_fecha"),
        fixed_receipts=fixed_receipts,
    )["saldo_actual"]
venta_dia_app = utils.month_expected_inflows(incomes, [], today[:7], today)["promedio_diario"]
compras_app = utils.average_monthly_purchases(invoices, today)

DEL_SISTEMA = {
    "sim_caja": float(utils.round2(caja_app)) if caja_app is not None else 0.0,
    "sim_venta": float(venta_dia_app),
    "sim_compras": float(compras_app),
}


def _cargar_del_sistema():
    for k, v in DEL_SISTEMA.items():
        st.session_state[k] = v


# Valores iniciales una sola vez; después mandan lo que escribas (o el botón).
st.session_state.setdefault("sim_credito", 220000.0)
for _k, _v in DEL_SISTEMA.items():
    st.session_state.setdefault(_k, _v)

h1, h2 = st.columns([3, 1])
h1.caption(
    "Caja, venta por día y compras salen de lo registrado en la app. Puedes cambiarlos para probar; "
    "el botón los vuelve a cargar con lo último registrado."
)
h2.button("🔄 Cargar datos del sistema", width="stretch", on_click=_cargar_del_sistema,
          help="Recalcula caja, venta promedio y compras promedio con lo registrado hasta este momento.")

s1, s2, s3, s4 = st.columns(4)
credito = s1.number_input("Monto del crédito (S/)", min_value=0.0, step=5000.0, format="%.0f", key="sim_credito")
caja_hoy = s2.number_input(
    "Caja real hoy (S/)", step=1000.0, format="%.0f", key="sim_caja",
    help="Efectivo + bancos de hoy. Sale con lo que calcula la app; cámbialo si tu caja real es otra.",
)
venta_dia = s3.number_input(
    "Venta por día (S/)", min_value=0.0, step=100.0, format="%.0f", key="sim_venta",
    help="Promedio de tus ventas registradas de los últimos 30 días (solo los días con registro).",
)
compras_mes = s4.number_input(
    "Compras a proveedores por mes (S/)", min_value=0.0, step=1000.0, format="%.0f", key="sim_compras",
    help="Promedio de tus facturas de los últimos 3 meses. Desde el tercer mes se usa esto como mínimo "
         "de pagos a proveedores, porque lo que compres desde hoy vence recién ahí (60-90 días).",
)
s2.caption(
    f"Según la app: {utils.money(caja_app)}" + (" · faltan ventas u otros ingresos por registrar" if caja_app < 0 else "")
    if caja_app is not None else "Configura el saldo inicial de caja en Configuración."
)
s3.caption(f"Según la app: {utils.money(venta_dia_app)}")
s4.caption(f"Según la app: {utils.money(compras_app)}")

# ---------- cuánto cancelar ----------
st.subheader("Cuánto le cancelas a cada deuda")
st.caption(
    "Pon solo el **capital** que le devuelves a cada una (máximo, lo que debes). El interés de este mes "
    "no va aquí: ya está en los pagos del mes en curso. Al pagarle, lo normal es que te pida capital + "
    "el interés del mes, y eso cuadra con el simulador."
)


def _poner(montos):
    for d in deudas:
        st.session_state[f"sim_pago_{d['id']}"] = float(montos.get(d["id"], 0.0))


def _mas_chicas(tope):
    """Las deudas más chicas completas mientras quepan en `tope`."""
    montos, usado = {}, 0.0
    for d in sorted(deudas, key=lambda x: x["saldo"]):
        if usado + d["saldo"] <= tope:
            montos[d["id"]] = d["saldo"]
            usado += d["saldo"]
    return montos


def _todo_lo_posible():
    montos, resto = {}, credito
    for d in sorted(deudas, key=lambda x: x["saldo"]):
        pago = min(d["saldo"], resto)
        if pago > 0:
            montos[d["id"]] = pago
            resto -= pago
    return montos


b1, b2, b3 = st.columns(3)
if b1.button("No cancelar nada", width="stretch", help="Pone todo en 0: no cancelas ninguna deuda y todo el crédito queda en caja."):
    _poner({})
if b2.button("Las más chicas", width="stretch", help="Cancela completas las deudas más chicas usando hasta el 70% del crédito."):
    _poner(_mas_chicas(credito * 0.7))
if b3.button("Todo lo posible", width="stretch", help="Usa todo el crédito, empezando por las más chicas."):
    _poner(_todo_lo_posible())

pagos = {}
cols = st.columns(2)
for i, d in enumerate(deudas):
    with cols[i % 2]:
        pagos[d["id"]] = st.number_input(
            f"{d['nombre']} · debes {utils.money(d['saldo'])} · cuota {utils.money(d['cuota'])}",
            min_value=0.0, max_value=float(d["saldo"]), step=5000.0, format="%.0f",
            key=f"sim_pago_{d['id']}",
            help="Solo capital. Desde el mes siguiente su cuota baja en proporción a lo que canceles.",
        )

r = utils.simulate_credit(
    utils.simulation_base(events, incomes, ingresos_esperados, deudas, venta_dia, compras_mes, today),
    deudas, pagos, caja_hoy, credito,
)
base_guardar = utils.simulate_credit(
    utils.simulation_base(events, incomes, ingresos_esperados, deudas, venta_dia, compras_mes, today),
    deudas, {}, caja_hoy, credito,
)

# ---------- resultado ----------
st.divider()


def _mes(m):
    return f"{utils.MONTHS_ES[int(m[5:7]) - 1][:3].capitalize()} {m[2:4]}"


k1, k2, k3, k4 = st.columns(4)
k1.metric("Crédito usado", utils.money(r["usado"]), f"quedan {utils.money(r['sobra_credito'])} en caja", delta_arrow="off",
          delta_color="off")
k2.metric(
    "Cuotas de estas deudas / mes", utils.money(r["cuota_despues"]),
    f"ahorras {utils.money(r['ahorro_mensual'])}" if r["ahorro_mensual"] else None,
    delta_arrow="off",
)
k3.metric("Deuda que queda", utils.money(r["deuda_restante"]))
k4.metric(
    "Caja más baja", utils.money(r["caja_minima"]),
    _mes(r["mes_minimo"]) if r["mes_minimo"] else None, delta_arrow="off", delta_color="off",
)

# Con qué caja arrancas: el sobrante del crédito NO queda aparte, se suma a la
# caja y se va usando para cubrir lo que falte cada mes.
st.markdown(
    f"**Arrancas con {utils.money(r['caja_arranque'])}** = caja de hoy {utils.money(caja_hoy)} "
    f"+ crédito {utils.money(credito)} − lo que cancelas {utils.money(r['usado'])}. "
    f"El sobrante del crédito ({utils.money(r['sobra_credito'])}) no queda aparte: se suma a tu caja "
    "y se va usando cada mes para cubrir lo que falte."
)

if r["usado"] > credito:
    st.error(f"Te pasas del crédito por {utils.money(r['usado'] - credito)}.")
elif r["mes_rojo"]:
    _i = next(i for i, s in enumerate(r["serie"]) if s["mes"] == r["mes_rojo"])
    _hasta = f"hasta **{_mes(r['serie'][_i - 1]['mes'])}**" if _i else "ni para este mes"
    st.warning(
        f"Tu caja y el sobrante del crédito alcanzan {_hasta}. Desde **{_mes(r['mes_rojo'])}** "
        "faltaría plata: lo negativo del gráfico es lo que tendrías que conseguir de otro lado."
    )
else:
    st.success("Con este escenario la caja alcanza en todos los meses simulados.")

if r["cambio_mensual_promedio"] < 0:
    st.info(
        f"Después de este mes, tu caja **baja en promedio {utils.money(-r['cambio_mensual_promedio'])} al mes**. "
        "Eso es lo que habría que ajustar para que se estabilice: comprar menos, vender más o bajar cuotas "
        "(por ejemplo, reprogramando un préstamo). Prueba bajando las compras arriba."
    )
elif r["cambio_mensual_promedio"] > 0:
    st.caption(f"Después de este mes, tu caja sube en promedio {utils.money(r['cambio_mensual_promedio'])} al mes.")

fig = go.Figure()
x = [_mes(s["mes"]) for s in r["serie"]]
fig.add_trace(go.Scatter(
    x=x, y=[s["caja_fin"] for s in r["serie"]], name="Este escenario", mode="lines+markers",
    line=dict(color="#0b5d68", width=3), fill="tozeroy", fillcolor="rgba(11,93,104,0.08)",
))
fig.add_trace(go.Scatter(
    x=x, y=[s["caja_fin"] for s in base_guardar["serie"]], name="Si no cancelas nada", mode="lines",
    line=dict(color="#8a959b", width=2, dash="dash"),
))
fig.add_hline(y=0, line_color="#b33f3f", line_width=1)
fig.update_layout(
    height=360, margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Caja a fin de mes (S/)",
    legend=dict(orientation="h", y=1.08), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, width="stretch")

st.dataframe(
    pd.DataFrame([
        {
            "Mes": _mes(s["mes"]) + (" (lo que falta)" if k == 0 else ""),
            "Ventas": utils.money(s["ventas"]),
            "Ingresos fijos": utils.money(s["fijos"]),
            "Proveedores": utils.money(s["proveedores"]),
            "Otros pagos": utils.money(s["otros"]),
            "Cuotas de estas deudas": utils.money(s["cuotas_deudas"]) if k else "como están registradas",
            "Caja a fin de mes": utils.money(s["caja_fin"]),
        }
        for k, s in enumerate(r["serie"])
    ]),
    hide_index=True, width="stretch",
)
st.caption(
    "Supuestos: el crédito entra este mes y lo que cancelas deja de cobrarse desde el mes siguiente. "
    "Cada deuda cobra su cuota sobre lo que queda (cancelar la mitad baja la cuota a la mitad). "
    "\"Otros pagos\" son los gastos fijos, préstamos bancarios y demás pendientes del Calendario; "
    "el mes en curso incluye lo atrasado. Ninguna cifra se guarda: no cambia nada en tus datos."
)
