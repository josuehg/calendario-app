import calendar as cal
from datetime import date
import streamlit as st
import db
import utils

st.title("📅 Calendario de pagos")

db.ensure_expense_instances()
invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
expenses = db.list_expenses()
track_contado = db.get_settings().get("track_contado", True)
events = utils.get_payment_events(invoices, letras, canje_facturas, track_contado, expenses)

today = date.today()
if "cal_year" not in st.session_state:
    st.session_state["cal_year"] = today.year
    st.session_state["cal_month"] = today.month

by_date = {}
for e in events:
    by_date.setdefault(e["date"], {"amount": 0.0, "count": 0, "items": []})
    by_date[e["date"]]["count"] += 1
    by_date[e["date"]]["items"].append(e)
for _info in by_date.values():
    _info["amount"] = utils.dsum(i["amount"] for i in _info["items"])

c1, c2, c3 = st.columns([1, 2, 1])
if c1.button("← Anterior"):
    m = st.session_state["cal_month"] - 1
    y = st.session_state["cal_year"]
    if m < 1:
        m, y = 12, y - 1
    st.session_state["cal_month"], st.session_state["cal_year"] = m, y
    st.rerun()
if c3.button("Siguiente →"):
    m = st.session_state["cal_month"] + 1
    y = st.session_state["cal_year"]
    if m > 12:
        m, y = 1, y + 1
    st.session_state["cal_month"], st.session_state["cal_year"] = m, y
    st.rerun()

y, m = st.session_state["cal_year"], st.session_state["cal_month"]
c2.markdown(f"<h3 style='text-align:center'>{utils.MONTHS_ES[m-1].capitalize()} {y}</h3>", unsafe_allow_html=True)

today_str = today.isoformat()
month_prefix = f"{y:04d}-{m:02d}"
month_items = [e for ds, info in by_date.items() if ds.startswith(month_prefix) for e in info["items"]]
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Total del mes", utils.money(utils.dsum(e["amount"] for e in month_items)))
mc2.metric("Vencido del mes", utils.money(utils.dsum(e["amount"] for e in month_items if e["date"] < today_str)))
mc3.metric("Por vencer del mes", utils.money(utils.dsum(e["amount"] for e in month_items if e["date"] >= today_str)))
mc4.metric("N° de pagos", len(month_items))

st.divider()

dow_cols = st.columns(7)
for i, d in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]):
    dow_cols[i].markdown(f"<div style='text-align:center;font-size:12px;color:gray;font-weight:600'>{d}</div>", unsafe_allow_html=True)

weeks = cal.Calendar(firstweekday=0).monthdayscalendar(y, m)

for week in weeks:
    cols = st.columns(7)
    for i, day in enumerate(week):
        with cols[i]:
            if day == 0:
                st.write("")
                continue
            ds = f"{y:04d}-{m:02d}-{day:02d}"
            info = by_date.get(ds)
            is_today = ds == today_str
            border = "2px solid #0b5d68" if is_today else "1px solid #d7dee1"
            if info:
                color = "#b33f3f" if ds < today_str else ("#b8802e" if (date.fromisoformat(ds) - today).days <= 7 else "#1b242b")
                st.markdown(
                    f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                    f"<div style='font-size:12px;color:gray'>{day}</div>"
                    f"<div style='font-family:monospace;font-size:12.5px;font-weight:600;color:{color}'>{utils.money(info['amount'])}</div>"
                    f"<div style='font-size:11px;color:gray'>{info['count']} pago(s)</div>"
                    f"</div>", unsafe_allow_html=True)
                if st.button("👁", key=f"day_{ds}", help="Ver pagos de este día"):
                    st.session_state["_cal_day"] = ds
                    st.rerun()
            else:
                st.markdown(
                    f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                    f"<div style='font-size:12px;color:gray'>{day}</div></div>", unsafe_allow_html=True)

st.divider()
st.markdown(
    "🔴 Vencido &nbsp;&nbsp; 🟠 Próximos 7 días &nbsp;&nbsp; ⚫ Más adelante",
)

st.divider()
st.subheader("Resumen semanal")
for week in weeks:
    days_in_week = [d for d in week if d != 0]
    if not days_in_week:
        continue
    ds_list = [f"{y:04d}-{m:02d}-{d:02d}" for d in days_in_week]
    week_items = [e for ds in ds_list for e in by_date.get(ds, {"items": []})["items"]]
    wc1, wc2, wc3 = st.columns([3, 1, 1])
    wc1.write(f"**{days_in_week[0]:02d} – {days_in_week[-1]:02d} de {utils.MONTHS_ES[m-1]}**")
    wc2.write(f"{len(week_items)} pago(s)")
    wc3.write(f"**{utils.money(utils.dsum(e['amount'] for e in week_items))}**")

if st.session_state.get("_cal_day"):
    ds = st.session_state["_cal_day"]
    day_events = by_date.get(ds, {"items": []})["items"]

    @st.dialog(f"Pagos del {utils.fmt_long(ds)}")
    def _day_dialog():
        for e in day_events:
            if e["kind"] == "expense":
                st.write(f"**{e['vendor']}** · {e['label']} · {e['branch']} · {utils.money(e['amount'])}")
            else:
                st.write(f"**{e['vendor']}** · Fact. {e['invoice_number']} · {e['branch']} · {e['label']} · {utils.money(e['amount'])}")
        if st.button("Cerrar"):
            st.session_state["_cal_day"] = None
            st.rerun()

    _day_dialog()
