import plotly.graph_objects as go
import streamlit as st
import db
import utils

st.title("📊 Presupuesto — próximas 13 semanas")
st.caption("En qué semana futura pega cada factura, letra o gasto (fijo y variable) pendiente.")

db.ensure_expense_instances()
invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
expenses = db.list_expenses()
track_contado = db.get_settings().get("track_contado", True)
events = utils.get_payment_events(invoices, letras, canje_facturas, track_contado, expenses)
buckets = utils.weekly_buckets(events)
today = utils.today_str()

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
    yaxis_title="Monto (S/)", xaxis_title="Semana (inicio)",
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
