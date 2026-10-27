import calendar as cal
from datetime import date

import streamlit as st
import db
import utils

st.title("📑 Estado de Egresos")
st.caption(
    "Egresos del mes por vencimiento/emisión (se hayan pagado o no todavía) "
    "— compras a proveedores + gastos operativos por categoría, como un "
    "estado de resultados de egresos."
)

today = date.today()
if "eg_year" not in st.session_state:
    st.session_state["eg_year"] = today.year
    st.session_state["eg_month"] = today.month

c1, c2, c3 = st.columns([1, 2, 1])
if c1.button("← Mes anterior"):
    m = st.session_state["eg_month"] - 1
    y = st.session_state["eg_year"]
    if m < 1:
        m, y = 12, y - 1
    st.session_state["eg_month"], st.session_state["eg_year"] = m, y
    st.rerun()
if c3.button("Mes siguiente →"):
    m = st.session_state["eg_month"] + 1
    y = st.session_state["eg_year"]
    if m > 12:
        m, y = 1, y + 1
    st.session_state["eg_month"], st.session_state["eg_year"] = m, y
    st.rerun()

y, m = st.session_state["eg_year"], st.session_state["eg_month"]
c2.markdown(f"<h3 style='text-align:center'>{utils.MONTHS_ES[m - 1].capitalize()} {y}</h3>", unsafe_allow_html=True)

periodo_inicio = f"{y:04d}-{m:02d}-01"
dias_mes = cal.monthrange(y, m)[1]
periodo_fin = f"{y:04d}-{m:02d}-{dias_mes:02d}"

invoices = db.list_invoices()
letras = db.list_letras()
expenses = db.list_expenses()
settings = db.get_settings()

estado = utils.expense_statement(
    invoices, letras, expenses, periodo_inicio, periodo_fin,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
)

st.divider()
st.subheader("🛒 Compras a proveedores")
st.metric("Total del mes", utils.money(estado["compras_proveedores"]))

st.divider()
st.subheader("💸 Gastos operativos")
cat_order = [c["name"] for c in db.list_expense_categories()]
categorias = [c for c in cat_order if c in estado["gastos_por_categoria"]]
categorias += [c for c in estado["gastos_por_categoria"] if c not in cat_order]

if not categorias:
    st.caption("No hay gastos operativos en este mes.")
else:
    for cat in categorias:
        gc1, gc2 = st.columns([3, 1])
        gc1.write(cat)
        gc2.write(utils.money(estado["gastos_por_categoria"][cat]))
    st.divider()
    sc1, sc2 = st.columns([3, 1])
    sc1.markdown("**Subtotal gastos operativos**")
    sc2.markdown(f"**{utils.money(estado['total_gastos_operativos'])}**")

st.divider()
tc1, tc2 = st.columns([3, 1])
tc1.markdown("### TOTAL EGRESOS DEL MES")
tc2.markdown(f"### {utils.money(estado['total_egresos'])}")

st.divider()
_filas = [{"Concepto": "Compras a proveedores", "Monto": estado["compras_proveedores"]}]
_filas += [{"Concepto": f"Gastos: {cat}", "Monto": monto} for cat, monto in estado["gastos_por_categoria"].items()]
_filas += [
    {"Concepto": "Subtotal gastos operativos", "Monto": estado["total_gastos_operativos"]},
    {"Concepto": "TOTAL EGRESOS", "Monto": estado["total_egresos"]},
]
st.download_button(
    "⬇️ Descargar (Excel)",
    data=utils.dict_list_to_xlsx_bytes({"Estado de egresos": _filas}),
    file_name=f"estado_egresos_{y:04d}-{m:02d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
