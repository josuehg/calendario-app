"""Compras del día: antes de colocar un pedido, ver cuánto queda del
presupuesto del mes y en qué mes caería el pago según el plazo."""
import pandas as pd
import streamlit as st

import db
import utils

st.title("🛒 Compras del día")
st.caption(
    "Antes de pedir: cuánto te queda de la meta de compras de este mes y, según el plazo del proveedor, en qué "
    "mes vencería el pago y si ese mes tiene espacio. Se actualiza con cada factura y letra que registres."
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
_ESTADO = {"ok": "🟢 Hay espacio", "caja": "🟠 Hay espacio, caja justa", "lleno": "🔴 Ese mes ya está lleno"}
st.dataframe(
    pd.DataFrame([
        {
            "Plazo del proveedor": f"{f['plazo']} días",
            "Vence": utils.fmt_long(f["vence"]) + (" ⚠️" if f["dias_1_10"] else ""),
            "Ya por pagar a proveedores ese mes": utils.money(f["ya_por_pagar"]),
            "Espacio (meta - ya comprometido)": utils.money(f["espacio"]),
            "Estado": _ESTADO[f["estado"]],
        }
        for f in v["filas"]
    ]),
    hide_index=True, width="stretch",
)
_mejor = max(v["filas"], key=lambda f: (f["espacio"], f["plazo"]))
if _mejor["espacio"] > 0:
    st.success(
        f"Hoy conviene pedir a **{_mejor['plazo']} días**: vence el {utils.fmt_long(_mejor['vence'])} y ese mes tiene "
        f"**{utils.money(_mejor['espacio'])}** de espacio."
        + (" Ojo: cae entre el 1 y el 10, cuando se pagan planilla, alquileres y bancos." if _mejor["dias_1_10"] else "")
    )
else:
    st.warning("Ningún plazo tiene espacio con esta meta: mejor esperar o cubrir con balanceo entre locales.")
st.caption("⚠️ Vence entre el 1 y el 10 del mes, cuando se juntan planilla, alquileres y cuotas bancarias.")

# ---------- próximos meses ----------
st.subheader("Pagos a proveedores de los próximos meses")
_filas = []
for k in range(1, 5):
    mes = utils._sumar_meses(today[:7], k)
    ya = utils.dsum(e["amount"] for e in events if e["kind"] in ("invoice", "letra") and e["date"][:7] == mes)
    espacio = max(0.0, utils.dsum([meta, -ya]))
    _filas.append({"Mes": _mes(mes), "Ya comprometido": utils.money(ya), "Meta": utils.money(meta),
                   "Espacio": utils.money(espacio),
                   "Estado": "🔴 Lleno" if espacio <= 0 else ("🟠 Poco espacio" if espacio < meta * 0.2 else "🟢 Con espacio")})
st.dataframe(pd.DataFrame(_filas), hide_index=True, width="stretch")
st.caption("Ya comprometido = facturas y letras pendientes que vencen ese mes. Espacio = meta de compras menos eso.")
