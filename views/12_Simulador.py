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
    "registradas y los ingresos fijos. No cambia tus datos; puedes guardar escenarios para compararlos."
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

_msg = st.session_state.pop("sim_msg", None)
if _msg:
    st.success(_msg)

escenarios = db.list_sim_scenarios()


def _cargar_escenario(esc):
    """Pone en los campos lo guardado en el escenario (corre antes de dibujar)."""
    d = esc.get("data") or {}
    for k in ("sim_credito", "sim_caja", "sim_venta", "sim_compras"):
        if d.get(k) is not None:
            st.session_state[k] = float(d[k])
    guardados = d.get("pagos") or {}
    for deuda in deudas:
        st.session_state[f"sim_pago_{deuda['id']}"] = float(min(guardados.get(str(deuda["id"]), 0), deuda["saldo"]))
    st.session_state["sim_inv_data"] = d.get("inversiones") or []
    st.session_state["sim_prov_data"] = d.get("prov_nuevas")
    st.session_state["sim_inv_ver"] = st.session_state.get("sim_inv_ver", 0) + 1
    st.session_state["sim_msg"] = f"Escenario cargado: {esc['name']}."


def _eliminar_escenario(esc):
    db.delete_sim_scenario(esc["id"])
    st.session_state["sim_msg"] = f"Escenario eliminado: {esc['name']}."


if escenarios:
    with st.expander(f"📂 Escenarios guardados ({len(escenarios)})"):
        e1, e2, e3 = st.columns([3, 1, 1])
        _por_nombre = {f"{e['name']} · {utils.fmt_time(e.get('created_at'))}": e for e in escenarios}
        _elegido = _por_nombre[e1.selectbox("Escenario", list(_por_nombre), label_visibility="collapsed", key="sim_esc_sel")]
        e2.button("Cargar", width="stretch", type="primary", on_click=_cargar_escenario, args=(_elegido,))
        e3.button("Eliminar", width="stretch", on_click=_eliminar_escenario, args=(_elegido,))

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
    "Meta de compras por mes (S/)", min_value=0.0, step=1000.0, format="%.0f", key="sim_compras",
    help="Sale del promedio de tus facturas de los últimos meses. Con esto se llena la tabla de compras nuevas por "
         "mes (más abajo), que luego puedes ajustar mes por mes.",
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

def _mes(m):
    return f"{utils.MONTHS_ES[int(m[5:7]) - 1][:3].capitalize()} {m[2:4]}"


# ---------- pagos a proveedores: lo registrado es fijo, lo nuevo se planea ----------
_base_registrado = utils.simulation_base(
    events, incomes, ingresos_esperados, deudas, venta_dia, compras_mes, today, compras_nuevas={},
)
_propuesta = utils.default_new_purchases(_base_registrado, compras_mes, today)
_plan_guardado = st.session_state.get("sim_prov_data")
st.subheader("🧾 Pagos a proveedores por mes")
_fijos_lbl = [f for f in _base_registrado if f["mes"] not in _propuesta]
st.caption(
    "Lo ya registrado (facturas y letras) es fijo. Lo nuevo es lo que pienses comprar desde hoy y vencería ese mes: "
    f"sale de tu meta de {utils.money(compras_mes)} al mes, pero puedes cambiarlo mes por mes "
    "(con balanceo de stock y mejores compras, debería bajar)."
    + (
        " " + " y ".join(f"{_mes(f['mes'])} ya está cerrado ({utils.money(f['prov_registrado'])})" for f in _fijos_lbl)
        + ": lo que pidas hoy vence recién después."
        if _fijos_lbl else ""
    )
)
_prov_df = pd.DataFrame([
    {
        "Mes": _mes(m),
        "Ya registrado (fijo)": next(f["prov_registrado"] for f in _base_registrado if f["mes"] == m),
        "Compras nuevas que vencen ese mes": float(
            (_plan_guardado or {}).get(m, _propuesta[m]) if _plan_guardado is not None else _propuesta[m]
        ),
    }
    for m in _propuesta
])
_prov_edit = st.data_editor(
    _prov_df, hide_index=True, width="stretch", num_rows="fixed",
    key=f"sim_prov_{int(compras_mes)}_{st.session_state.get('sim_inv_ver', 0)}",
    disabled=["Mes", "Ya registrado (fijo)"],
    column_config={
        "Ya registrado (fijo)": st.column_config.NumberColumn(format="%.0f"),
        "Compras nuevas que vencen ese mes": st.column_config.NumberColumn(min_value=0, step=1000, format="%.0f"),
    },
)
compras_nuevas = {
    m: float(v) if pd.notna(v) else 0.0
    for m, v in zip(_propuesta, _prov_edit["Compras nuevas que vencen ese mes"])
}
_total_prov = _prov_edit["Ya registrado (fijo)"] + _prov_edit["Compras nuevas que vencen ese mes"].fillna(0)
st.caption(
    "Total a proveedores: "
    + " · ".join(f"{fila['Mes']} {utils.money(t)}" for (_, fila), t in zip(_prov_edit.iterrows(), _total_prov))
    + ". Si cambias la meta de compras de arriba, esta tabla se vuelve a llenar con la nueva meta."
)

base = utils.simulation_base(
    events, incomes, ingresos_esperados, deudas, venta_dia, compras_mes, today, compras_nuevas=compras_nuevas,
)


# ---------- inversiones ----------
st.subheader("Inversiones")
st.caption(
    "Plata que separas para mejorar el negocio. Sale de la caja en el mes que elijas. Si esperas "
    "recuperar algo (por ejemplo, mercadería de temporada que se vende), pon cuánto y en qué mes vuelve. "
    "Agrega o borra filas como quieras."
)
_meses_lbl = {_mes(f["mes"]): f["mes"] for f in base}
_lbls = list(_meses_lbl)
_mes_inv = _lbls[1] if len(_lbls) > 1 else _lbls[0]
_lbl_de_mes = {v: k for k, v in _meses_lbl.items()}
if "sim_inv_data" in st.session_state:
    # De un escenario guardado: un mes que ya pasó (fuera de la proyección) queda vacío.
    _filas = [
        {"Concepto": i.get("concepto") or "", "Monto (S/)": i.get("monto"), "Mes": _lbl_de_mes.get(i.get("mes")),
         "Recupera (S/)": i.get("recupera") or None, "Mes en que recupera": _lbl_de_mes.get(i.get("mes_recupera"))}
        for i in st.session_state["sim_inv_data"]
    ]
else:
    _filas = [
        {"Concepto": "Mejoras Odoo (compras, balanceo de stock)", "Monto (S/)": 10000.0, "Mes": _mes_inv,
         "Recupera (S/)": None, "Mes en que recupera": None},
        {"Concepto": "Línea Dermosol (temporada)", "Monto (S/)": 5000.0, "Mes": _mes_inv,
         "Recupera (S/)": None, "Mes en que recupera": None},
    ]
INV_INICIAL = pd.DataFrame(
    _filas, columns=["Concepto", "Monto (S/)", "Mes", "Recupera (S/)", "Mes en que recupera"],
)
# Tipos explícitos: así las celdas vacías se ven vacías y no como "None".
INV_INICIAL["Recupera (S/)"] = INV_INICIAL["Recupera (S/)"].astype("float")
INV_INICIAL["Mes en que recupera"] = INV_INICIAL["Mes en que recupera"].astype("string")
inv_df = st.data_editor(
    INV_INICIAL, key=f"sim_inversiones_{st.session_state.get('sim_inv_ver', 0)}", num_rows="dynamic", hide_index=True, width="stretch",
    column_config={
        "Concepto": st.column_config.TextColumn(required=True),
        "Monto (S/)": st.column_config.NumberColumn(min_value=0, step=500, format="%.0f"),
        "Mes": st.column_config.SelectboxColumn(options=_lbls, required=True),
        "Recupera (S/)": st.column_config.NumberColumn(
            min_value=0, step=500, format="%.0f", help="Opcional: lo que esperas que vuelva (ventas de esa mercadería)."
        ),
        "Mes en que recupera": st.column_config.SelectboxColumn(options=_lbls),
    },
)
inversiones = [
    {
        "concepto": str(row["Concepto"]) if pd.notna(row["Concepto"]) else "",
        "monto": float(row["Monto (S/)"] or 0),
        "mes": _meses_lbl.get(row["Mes"]),
        "recupera": float(row["Recupera (S/)"]) if pd.notna(row["Recupera (S/)"]) else 0.0,
        "mes_recupera": _meses_lbl.get(row["Mes en que recupera"]) if pd.notna(row["Mes en que recupera"]) else None,
    }
    for _, row in inv_df.iterrows()
    if pd.notna(row["Monto (S/)"]) and row["Monto (S/)"] and pd.notna(row["Mes"])
]

r = utils.simulate_credit(base, deudas, pagos, caja_hoy, credito, inversiones)
base_guardar = utils.simulate_credit(base, deudas, {}, caja_hoy, credito, inversiones)

# ---------- resultado ----------
st.divider()

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
    + (
        f" Las inversiones ({utils.money(r['total_inversiones'])}) salen de la caja en su mes"
        + (f" y vuelven {utils.money(r['total_recupera'])}" if r["total_recupera"] else "")
        + "."
        if r["total_inversiones"] else ""
    )
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

ajuste = utils.adjustment_to_stay_positive(r["serie"])
if ajuste["compras_mes"] or ajuste["venta_mes"] or ajuste["extra_inicio"]:
    _mes2 = _mes(r["serie"][2]["mes"]) if len(r["serie"]) > 2 else "más adelante"
    _lineas = ["**🎯 Para que tu caja no entre en rojo necesitas, una de estas:**"]
    if ajuste["extra_inicio"]:
        _lineas.append(
            f"- Primero, conseguir **{utils.money(ajuste['extra_inicio'])} ya** (más crédito, cobrar antes o "
            "postergar algún pago): los primeros meses quedan en rojo antes de que comprar menos llegue a notarse."
        )
    if ajuste["compras_mes"] and ajuste["compras_mes"] > compras_mes:
        _lineas.append(
            f"- Solo con comprar menos **no alcanza**: harían falta {utils.money(ajuste['compras_mes'])} menos al mes "
            f"y compras {utils.money(compras_mes)}."
        )
    elif ajuste["compras_mes"]:
        _lineas.append(
            f"- **Comprar {utils.money(ajuste['compras_mes'])} menos cada mes** (de "
            f"{utils.money(compras_mes)} a {utils.money(max(compras_mes - ajuste['compras_mes'], 0))}). "
            f"Se nota en caja desde {_mes2}, cuando vence lo que compres desde hoy."
        )
    if ajuste["venta_mes"]:
        _lineas.append(
            f"- O **vender {utils.money(ajuste['venta_dia'])} más por día** ({utils.money(ajuste['venta_mes'])} al mes)"
            + (f", y además conseguir {utils.money(ajuste['extra_inicio_ventas'])} para este mes"
               if ajuste["extra_inicio_ventas"] else "")
            + "."
        )
    _lineas.append("También sirve combinarlas (la mitad con compras y la mitad con ventas) o bajar cuotas reprogramando un préstamo.")
    st.info("\n\n".join(_lineas))
elif r["cambio_mensual_promedio"] < 0:
    st.info(
        f"Tu caja no entra en rojo, pero después de este mes **baja en promedio "
        f"{utils.money(-r['cambio_mensual_promedio'])} al mes**: vigílalo."
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
            "Inversiones": utils.money(s["inversiones"]) if s["inversiones"] else "—",
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
    "el mes en curso incluye lo atrasado. Nada de esto cambia tus datos; solo se guarda el escenario si "
    "pulsas Guardar escenario."
)

# ---------- ventanas de compra ----------
st.divider()
st.subheader("🛒 Ventanas de compra (hoy)")
ventanas = utils.purchase_windows(events, invoices, r["serie"], compras_mes, today, plan=compras_nuevas)
st.caption(
    f"Si colocas un pedido hoy, en qué mes vence según el plazo y cuánto espacio queda ese mes según tu plan de "
    "compras nuevas (la tabla de Pagos a proveedores por mes: cámbiala y esta se ajusta)."
)
_ESTADO = {
    "ok": "🟢 Hay espacio",
    "caja": "🟠 Hay espacio, pero tu caja está en rojo desde ese mes",
    "lleno": "🔴 Ese mes ya está lleno",
}
st.dataframe(
    pd.DataFrame([
        {
            "Si pides hoy a…": f"{v['plazo']} días",
            "Vence": utils.fmt_long(v["vence"]) + (" ⚠️" if v["dias_1_10"] else ""),
            "Ya por pagar a proveedores ese mes": utils.money(v["ya_por_pagar"]),
            "Espacio según tu plan": utils.money(v["espacio"]),
            "Estado": _ESTADO[v["estado"]],
        }
        for v in ventanas["filas"]
    ]),
    hide_index=True, width="stretch",
)
_m_actual = utils.MONTHS_ES[int(today[5:7]) - 1]
st.caption(
    f"⚠️ Vence entre el 1 y el 10, cuando ya pagas planilla, alquileres, bancos y la hipoteca: mejor que caiga "
    f"después del 10. · En {_m_actual} ya colocaste {utils.money(ventanas['comprado_este_mes'])} en facturas: "
    f"te quedan **{utils.money(ventanas['queda_este_mes'])}** de tu meta para este mes."
)

# ---------- guardar este escenario ----------
st.divider()
with st.form("sim_guardar", clear_on_submit=True, border=False):
    g1, g2 = st.columns([3, 1])
    nombre = g1.text_input("Nombre del escenario", placeholder="Plan B: China + Marlene + KR Carmen")
    if g2.form_submit_button("💾 Guardar escenario", width="stretch"):
        if not nombre.strip():
            st.warning("Ponle un nombre al escenario.")
        else:
            db.create_sim_scenario({
                "name": nombre.strip(),
                "data": {
                    "sim_credito": credito, "sim_caja": caja_hoy, "sim_venta": venta_dia, "sim_compras": compras_mes,
                    "pagos": {str(k): v for k, v in pagos.items() if v},
                    "inversiones": inversiones,
                    "prov_nuevas": compras_nuevas,
                },
            })
            st.session_state["sim_msg"] = f"Escenario guardado: {nombre.strip()}. Lo encuentras arriba, en Escenarios guardados."
            st.rerun()
