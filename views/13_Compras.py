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


def _sobra(mes):
    return utils.month_cash_room(events, incomes, ingresos_esperados, mes, today)


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
_metas = {}
for e in escenarios:
    d = e.get("data") or {}
    if d.get("sim_compras"):
        _metas[e["name"]] = float(d["sim_compras"])
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
st.caption(f"Tu promedio de compras de los últimos meses es {utils.money(promedio)}.")

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
            "Caja que sobra ese mes": utils.money(f["sobra"]),
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
    "Caja que sobra ese mes = venta esperada + ingresos fijos − todo lo pendiente de ese mes (proveedores, planilla, "
    "alquileres, préstamos…), igual que el Neto proyectado del Calendario. Puedes pedir = el menor entre la meta y la "
    "caja. ⚠️ Vence entre el 1 y el 10 del mes, cuando se juntan planilla, alquileres y cuotas bancarias."
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
                   "Espacio en la meta": utils.money(espacio), "Caja que sobra": utils.money(sobra),
                   "Puedes pedir": utils.money(puedes),
                   "Estado": _estado(espacio, puedes) if puedes < espacio or espacio <= 0
                   else ("🟠 Poco espacio" if espacio < meta * 0.2 else "🟢 Con espacio")})
st.dataframe(pd.DataFrame(_filas), hide_index=True, width="stretch")
st.caption(
    "Ya comprometido = facturas y letras pendientes que vencen ese mes. Espacio en la meta = meta menos eso. "
    "Caja que sobra = lo que queda ese mes después de TODOS los pagos (sin compras nuevas). Puedes pedir = el menor."
)
