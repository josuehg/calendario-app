"""Compras del día: antes de colocar un pedido, ver cuánto queda del
presupuesto del mes y en qué mes caería el pago según el plazo."""
import pandas as pd
import streamlit as st

import db
import utils

st.title("🛒 Compras del día")
st.caption(
    "Antes de pedir: cuánto te queda de la meta de compras de este mes y, según el plazo del proveedor, en qué "
    "mes vencería el pago y si ese mes tiene espacio en la meta **y** en la caja. Se actualiza con cada factura, "
    "letra, gasto y venta que registres."
)

invoices = db.list_invoices()
letras = db.list_letras()
settings = db.get_settings()
events = utils.get_payment_events(
    invoices, letras, db.list_canje_facturas(), settings.get("track_contado", True), db.list_expenses(),
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
    letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
)
today = utils.today_str()
incomes = db.list_incomes()
ingresos_esperados = utils.fixed_income_expected(db.list_fixed_incomes(), db.list_fixed_income_receipts(),
                                                 months_ahead=8)


_eventos_plan = events  # se reemplaza abajo si la meta sale de un escenario
_credito = 0.0          # el crédito del plan, si la meta sale de un escenario
_caja = None
if settings.get("caja_saldo_inicial_fecha"):
    _caja = utils.compute_cash_balance(
        invoices, letras, db.list_expenses(), incomes,
        saldo_inicial=settings.get("caja_saldo_inicial") or 0.0,
        saldo_inicial_fecha=settings.get("caja_saldo_inicial_fecha"),
        fixed_receipts=db.list_fixed_income_receipts(),
    )["saldo_actual"]
_disponible = {}


def _sobra(mes):
    """Caja disponible para compras nuevas que se paguen ese mes (con arrastre)."""
    if mes not in _disponible:
        _meses = [utils._sumar_meses(today[:7], k) for k in range(0, 8)]
        _disponible.update(utils.cash_available_by_month(
            _eventos_plan, incomes, ingresos_esperados, meta, (_caja or 0.0) + _credito, _meses, today))
    return _disponible.get(mes, 0.0)


def _estado(espacio, puedes):
    if espacio <= 0:
        return "🔴 Meta llena"
    if puedes <= 0:
        return "🔴 La caja no alcanza"
    if puedes < espacio:
        return "🟠 Limita la caja"
    return "🟢 Hay espacio"


def _mes(m):
    return f"{utils.MONTHS_ES[int(m[5:7]) - 1].capitalize()} {m[:4]}"


# ---------- meta de compras: del plan guardado o a mano ----------
escenarios = db.list_sim_scenarios()
_metas, _datos = {}, {}
for e in escenarios:
    d = e.get("data") or {}
    if d.get("sim_compras"):
        _metas[e["name"]] = float(d["sim_compras"])
        _datos[e["name"]] = d
promedio = utils.average_monthly_purchases(invoices, today)
opciones = list(_metas) + ["Escribirla a mano"]
_def = next((i for i, n in enumerate(opciones) if "FINAL" in n.upper()), 0)
c1, c2 = st.columns([2, 1])
origen = c1.selectbox("Meta de compras del mes, según", opciones, index=_def, key="cd_origen",
                      help="Toma la meta de compras de un escenario guardado del Simulador, o escríbela.")
if origen == "Escribirla a mano" or not _metas:
    meta = c2.number_input("Meta de compras por mes (S/)", min_value=0.0, step=1000.0, format="%.0f",
                           value=float(round(promedio, -3)), key="cd_meta")
else:
    meta = _metas[origen]
    c2.metric("Meta de compras por mes", utils.money(meta))
    # La caja se ve como queda CON el plan: las deudas que el plan cancela
    # (con el crédito o con renovaciones) dejan de cobrar su cuota.
    _deudas = utils.simulator_debts(db.list_debts(active_only=True), db.list_fixed_expenses())
    _cuotas_plan = utils.plan_debt_cuotas(_datos[origen], _deudas)
    _eventos_plan = utils.apply_plan_cuotas(events, _cuotas_plan, today)
    _credito = float(_datos[origen].get("sim_credito") or 0)
    _nombres = {str(d["fixed_expense_id"]): d["nombre"] for d in _deudas if d.get("fixed_expense_id")}
    _canc = [_nombres.get(k, "?") for k, v in _cuotas_plan.items() if float(v.get("factor", 1)) == 0]
    _renov = [f"{_nombres.get(k, '?')} ({_mes(v['cancel_mes'])})" for k, v in _cuotas_plan.items()
              if v.get("cancel_mes") and float(v.get("factor", 1)) > 0]
    if _canc or _renov:
        st.caption(
            f"La caja de cada mes se calcula **según {origen}**: "
            + (f"desde el próximo mes ya no se cuentan las cuotas de {', '.join(_canc)} (las cancela el crédito)"
               if _canc else "")
            + ("; " if _canc and _renov else "")
            + (f"con renovaciones se cancelan {', '.join(_renov)}" if _renov else "")
            + ". El Calendario sigue mostrando lo registrado hoy."
        )
st.caption(f"Tu promedio de compras de los últimos meses es {utils.money(promedio)}.")
st.caption(
    f"Caja de partida: {utils.money(_caja) if _caja is not None else 'sin configurar (Simulador → ✏️ Corregir caja)'}"
    + (f" + crédito del plan {utils.money(_credito)}" if _credito else "")
    + ". Mes a mes se le suma lo que sobra y se le restan las compras del plan de los meses anteriores."
)

# ---------- presupuesto del mes ----------
plazos = (30, 60, 75, 90)
v = utils.purchase_windows(events, invoices, [], meta, today, plazos=plazos)
st.subheader(f"Presupuesto de {utils.MONTHS_ES[int(today[5:7]) - 1]}")
p1, p2, p3 = st.columns(3)
p1.metric("Meta del mes", utils.money(meta))
p2.metric("Ya pedido (facturas del mes)", utils.money(v["comprado_este_mes"]))
p3.metric("Te queda para pedir", utils.money(v["queda_este_mes"]))
avance = min(v["comprado_este_mes"] / meta, 1.0) if meta else 0.0
st.progress(avance, text=f"{avance * 100:.0f}% de la meta usada")
if meta and v["comprado_este_mes"] > meta:
    st.error(f"Ya te pasaste de la meta por {utils.money(v['comprado_este_mes'] - meta)}. Frena pedidos y prioriza balanceo.")

# ---------- según el plazo ----------
st.subheader("Si pido hoy, ¿cuándo se paga?")
for f in v["filas"]:
    f["sobra"] = _sobra(f["mes"])
    f["puedes"] = utils.with_cash_limit(f["espacio"], f["sobra"])
st.dataframe(
    pd.DataFrame([
        {
            "Plazo del proveedor": f"{f['plazo']} días",
            "Vence": utils.fmt_long(f["vence"]) + (" ⚠️" if f["dias_1_10"] else ""),
            "Ya por pagar a proveedores ese mes": utils.money(f["ya_por_pagar"]),
            "Espacio en la meta": utils.money(f["espacio"]),
            "Caja disponible ese mes": utils.money(f["sobra"]),
            "Puedes pedir": utils.money(f["puedes"]),
            "Estado": _estado(f["espacio"], f["puedes"]),
        }
        for f in v["filas"]
    ]),
    hide_index=True, width="stretch",
)
_mejor = max(v["filas"], key=lambda f: (f["puedes"], f["plazo"]))
if _mejor["puedes"] > 0:
    st.success(
        f"Hoy conviene pedir a **{_mejor['plazo']} días**: vence el {utils.fmt_long(_mejor['vence'])} y ese mes "
        f"puedes pedir hasta **{utils.money(_mejor['puedes'])}**."
        + (" Ojo: cae entre el 1 y el 10, cuando se pagan planilla, alquileres y bancos." if _mejor["dias_1_10"] else "")
    )
else:
    st.warning("Ningún plazo tiene espacio con esta meta y esta caja: mejor esperar o cubrir con balanceo entre locales.")
st.caption(
    "Caja disponible ese mes = caja de partida (+ crédito del plan) + lo que sobra cada mes hasta ese (venta esperada "
    "+ ingresos fijos − todos los pagos, como el Neto proyectado del Calendario) − las compras del plan de los meses "
    "anteriores. Puedes pedir = el menor entre la meta y esa caja. ⚠️ Vence entre el 1 y el 10 del mes, cuando se "
    "juntan planilla, alquileres y cuotas bancarias."
)

# ---------- solo para emergencias: letra pagada dentro de los días de gracia ----------
gracia = int(settings.get("letra_dias_gracia_max") or 0)
if gracia:
    with st.expander(f"🚨 Solo si es urgente: letra pagada hasta {gracia} días después (con recargo del banco)"):
        st.caption(
            "No es lo recomendable: el banco cobra un recargo por pagar la letra después de su vencimiento. Sirve para "
            "saber si, ante una urgencia de stock, algún plazo tiene espacio corriendo el pago dentro de los días de gracia."
        )
        filas_emerg = []
        for plazo in (60, 75, 90):
            vence = utils.add_days(today, plazo + gracia)
            mes = vence[:7]
            ya = utils.dsum(e["amount"] for e in events if e["kind"] in ("invoice", "letra") and e["date"][:7] == mes)
            espacio = max(0.0, utils.dsum([meta, -ya]))
            puedes = utils.with_cash_limit(espacio, _sobra(mes))
            filas_emerg.append({
                "Plazo": f"{plazo} + {gracia} días",
                "Se pagaría": utils.fmt_long(vence) + (" ⚠️" if int(vence[8:10]) <= 10 else ""),
                "Ya por pagar a proveedores ese mes": utils.money(ya),
                "Espacio en la meta": utils.money(espacio),
                "Puedes pedir": utils.money(puedes),
                "Estado": "🟡 Hay espacio (con recargo)" if puedes > 0 else _estado(espacio, puedes),
            })
        st.dataframe(pd.DataFrame(filas_emerg), hide_index=True, width="stretch")

# ---------- próximos meses ----------
st.subheader("Pagos a proveedores de los próximos meses")
_filas = []
for k in range(1, 5):
    mes = utils._sumar_meses(today[:7], k)
    ya = utils.dsum(e["amount"] for e in events if e["kind"] in ("invoice", "letra") and e["date"][:7] == mes)
    espacio = max(0.0, utils.dsum([meta, -ya]))
    sobra = _sobra(mes)
    puedes = utils.with_cash_limit(espacio, sobra)
    _filas.append({"Mes": _mes(mes), "Ya comprometido": utils.money(ya), "Meta": utils.money(meta),
                   "Espacio en la meta": utils.money(espacio), "Caja disponible": utils.money(sobra),
                   "Puedes pedir": utils.money(puedes),
                   "Estado": _estado(espacio, puedes) if puedes < espacio or espacio <= 0
                   else ("🟠 Poco espacio" if espacio < meta * 0.2 else "🟢 Con espacio")})
st.dataframe(pd.DataFrame(_filas), hide_index=True, width="stretch")
st.caption(
    "Ya comprometido = facturas y letras pendientes que vencen ese mes. Espacio en la meta = meta menos eso. "
    "Caja disponible = con lo que llegas a ese mes más lo que sobra en él después de TODOS los pagos. "
    "Puedes pedir = el menor entre eso y el espacio en la meta."
)
