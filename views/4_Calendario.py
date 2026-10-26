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

TIPOS_CAL = ["Todos", "Facturas a crédito", "Contado", "Letras", "Gastos fijos", "Gastos variables"]
fc1, fc2 = st.columns(2)
f_tipo_cal = fc1.selectbox("Tipo", TIPOS_CAL, key="cal_f_tipo")
categorias_cal = ["Todas"] + [c["name"] for c in db.list_expense_categories()]
f_cat_cal = fc2.selectbox("Categoría (solo gastos)", categorias_cal, key="cal_f_categoria")


def _cal_matches(e):
    if f_tipo_cal == "Facturas a crédito" and not (e["kind"] == "invoice" and e.get("doc_type") == "credito"):
        return False
    if f_tipo_cal == "Contado" and not (e["kind"] == "invoice" and e.get("doc_type") == "contado"):
        return False
    if f_tipo_cal == "Letras" and e["kind"] != "letra":
        return False
    if f_tipo_cal == "Gastos fijos" and not (e["kind"] == "expense" and e.get("expense_kind") == "fijo"):
        return False
    if f_tipo_cal == "Gastos variables" and not (e["kind"] == "expense" and e.get("expense_kind") == "variable"):
        return False
    if f_cat_cal != "Todas" and e.get("category") != f_cat_cal:
        return False
    return True


events = [e for e in events if _cal_matches(e)]

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

vista = st.radio("Vista", ["📅 Mes", "📋 Lista"], horizontal=True, key="cal_vista")

weeks = cal.Calendar(firstweekday=0).monthdayscalendar(y, m)
DOW_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _day_color(ds):
    return "#b33f3f" if ds < today_str else ("#b8802e" if (date.fromisoformat(ds) - today).days <= 7 else "#1b242b")


if vista == "📅 Mes":
    dow_cols = st.columns(7)
    for i, d in enumerate(DOW_ES):
        dow_cols[i].markdown(f"<div style='text-align:center;font-size:12px;color:gray;font-weight:600'>{d}</div>", unsafe_allow_html=True)

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
                    st.markdown(
                        f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                        f"<div style='font-size:12px;color:gray'>{day}</div>"
                        f"<div style='font-family:monospace;font-size:12.5px;font-weight:600;color:{_day_color(ds)}'>{utils.money(info['amount'])}</div>"
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
else:
    # Vista de lista: un renglón por día con pagos, más cómoda en celular o
    # cuando hay mucho que revisar en un mes (en vez de un grid apretado).
    days_in_month = cal.monthrange(y, m)[1]
    hubo_algun_dia = False
    for day in range(1, days_in_month + 1):
        ds = f"{y:04d}-{m:02d}-{day:02d}"
        info = by_date.get(ds)
        if not info:
            continue
        hubo_algun_dia = True
        dow_label = DOW_ES[date.fromisoformat(ds).weekday()]
        with st.container(border=True):
            lc1, lc2, lc3, lc4 = st.columns([2.2, 1.3, 1, 1])
            tag = " 🟢" if ds == today_str else ""
            lc1.markdown(f"**{dow_label} {day:02d} de {utils.MONTHS_ES[m-1]}**{tag}")
            lc2.markdown(
                f"<span style='font-family:monospace;font-weight:600;color:{_day_color(ds)}'>{utils.money(info['amount'])}</span>",
                unsafe_allow_html=True,
            )
            lc3.write(f"{info['count']} pago(s)")
            if lc4.button("Ver", key=f"list_day_{ds}", width="stretch"):
                st.session_state["_cal_day"] = ds
                st.rerun()
    if not hubo_algun_dia:
        st.caption("No hay pagos este mes con estos filtros.")
    st.divider()
    st.markdown(
        "🔴 Vencido &nbsp;&nbsp; 🟠 Próximos 7 días &nbsp;&nbsp; ⚫ Más adelante",
    )

_CAL_ACTION_KEYS = ["_cal_pay_target", "_cal_edit_target", "_cal_del_target", "_cal_bulk_pay_targets"]

# Un solo diálogo a la vez: mientras se paga/edita/elimina algo, se cierra el del día.
if st.session_state.get("_cal_day") and not any(st.session_state.get(k) for k in _CAL_ACTION_KEYS):
    ds = st.session_state["_cal_day"]
    day_events = by_date.get(ds, {"items": []})["items"]

    @st.dialog(f"Pagos del {utils.fmt_long(ds)}")
    def _day_dialog():
        seleccionadas = []
        for e in day_events:
            with st.container(border=True):
                cb_col, info_col = st.columns([0.4, 4.6])
                marcada = cb_col.checkbox(
                    "sel", key=f"cal_sel_{e['kind']}_{e['ref_id']}", label_visibility="collapsed",
                )
                if marcada:
                    seleccionadas.append(e)
                with info_col:
                    if e["kind"] == "expense":
                        st.write(f"**{e['vendor']}** · {e['label']} · {e['branch']} · {utils.money(e['amount'])}")
                    else:
                        st.write(f"**{e['vendor']}** · Fact. {e['invoice_number']} · {e['branch']} · {e['label']} · {utils.money(e['amount'])}")
                bc1, bc2, bc3 = st.columns(3)
                if bc1.button("Pagado", key=f"cal_pay_{e['kind']}_{e['ref_id']}", width="stretch"):
                    st.session_state["_cal_pay_target"] = e
                    st.rerun()
                if bc2.button("Editar", key=f"cal_edit_{e['kind']}_{e['ref_id']}", width="stretch"):
                    st.session_state["_cal_edit_target"] = e
                    st.rerun()
                if bc3.button("Eliminar", key=f"cal_del_{e['kind']}_{e['ref_id']}", width="stretch"):
                    st.session_state["_cal_del_target"] = e
                    st.rerun()

        if len(day_events) > 1:
            st.divider()
            n = len(seleccionadas)
            if st.button(
                f"✅ Marcar {n} seleccionada(s) como pagadas" if n else "✅ Marcar seleccionadas como pagadas",
                type="primary", width="stretch", disabled=n == 0,
            ):
                st.session_state["_cal_bulk_pay_targets"] = seleccionadas
                st.rerun()

        if st.button("Cerrar"):
            st.session_state["_cal_day"] = None
            st.rerun()

    _day_dialog()

# ---------- diálogo: marcar varias como pagadas de una sola vez ----------
if st.session_state.get("_cal_bulk_pay_targets"):
    _targets = st.session_state["_cal_bulk_pay_targets"]

    @st.dialog("Marcar varias como pagadas")
    def _cal_bulk_pay_dialog():
        st.write(f"Se marcarán **{len(_targets)}** pago(s) como pagados, con la misma fecha:")
        for t in _targets:
            st.caption(f"· {t['vendor']} · {t['label']} · {utils.money(t['amount'])}")
        st.markdown(f"**Total: {utils.money(utils.dsum(t['amount'] for t in _targets))}**")
        fecha = st.date_input("Fecha de pago (se aplica a todas)", value=None, key="cal_bulk_pay_fecha")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", width="stretch"):
            st.session_state["_cal_bulk_pay_targets"] = None
            st.rerun()
        if c2.button(f"Confirmar pago de {len(_targets)}", type="primary", width="stretch"):
            fecha_str = (fecha or date.today()).isoformat()
            actor = utils.current_actor()
            for t in _targets:
                if t["kind"] == "letra":
                    db.mark_letra_paid(t["ref_id"], fecha_str, paid_by=actor)
                elif t["kind"] == "expense":
                    db.set_expense_status(t["ref_id"], "pagado", paid_at=fecha_str, paid_by=actor)
                else:
                    db.mark_invoice_paid(t["ref_id"], fecha_str, paid_by=actor)
                st.session_state.pop(f"cal_sel_{t['kind']}_{t['ref_id']}", None)
            st.session_state["_cal_bulk_pay_targets"] = None
            st.rerun()

    _cal_bulk_pay_dialog()

# ---------- diálogo: confirmar pago (se puede abrir desde el del día) ----------
if st.session_state.get("_cal_pay_target"):
    _pe = st.session_state["_cal_pay_target"]

    @st.dialog("Marcar como pagado")
    def _cal_pay_dialog():
        st.write(f"**{_pe['vendor']}** · {_pe['label']} · {utils.money(_pe['amount'])}")
        fecha = st.date_input("Fecha de pago", value=None, key="cal_pay_fecha")
        col_a, col_b = st.columns(2)
        if col_a.button("Cancelar", width="stretch"):
            st.session_state["_cal_pay_target"] = None
            st.rerun()
        if col_b.button("Confirmar pago", type="primary", width="stretch"):
            fecha_str = (fecha or date.today()).isoformat()
            actor = utils.current_actor()
            if _pe["kind"] == "letra":
                db.mark_letra_paid(_pe["ref_id"], fecha_str, paid_by=actor)
            elif _pe["kind"] == "expense":
                db.set_expense_status(_pe["ref_id"], "pagado", paid_at=fecha_str, paid_by=actor)
            else:
                db.mark_invoice_paid(_pe["ref_id"], fecha_str, paid_by=actor)
            st.session_state["_cal_pay_target"] = None
            st.rerun()

    _cal_pay_dialog()

# ---------- diálogo: editar monto/fecha rápido ----------
if st.session_state.get("_cal_edit_target"):
    _ee = st.session_state["_cal_edit_target"]

    @st.dialog("Editar")
    def _cal_edit_dialog():
        st.caption(f"{_ee['vendor']} · {_ee['label']}")
        st.caption(
            "Aquí solo se ajusta monto y fecha. Para cambiar otros datos "
            "(proveedor, categoría, etc.) ve a la pantalla correspondiente."
        )
        monto = st.number_input(
            "Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
            value=float(_ee["amount"]), key="cal_edit_monto",
        )
        fecha = st.date_input("Fecha", value=date.fromisoformat(_ee["date"]), key="cal_edit_fecha")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", width="stretch"):
            st.session_state["_cal_edit_target"] = None
            st.rerun()
        if c2.button("Guardar", type="primary", width="stretch"):
            monto_r = utils.round2(monto)
            fecha_str = fecha.isoformat()
            if _ee["kind"] == "invoice":
                db.update_invoice(_ee["ref_id"], {"amount": monto_r, "due_date": fecha_str})
            elif _ee["kind"] == "letra":
                db.update_letra(_ee["ref_id"], {"monto": monto_r, "fecha_vencimiento": fecha_str})
            else:
                db.update_expense(_ee["ref_id"], {"amount": monto_r, "due_date": fecha_str})
            st.session_state["_cal_edit_target"] = None
            st.rerun()

    _cal_edit_dialog()

# ---------- diálogo: eliminar con confirmación ----------
if st.session_state.get("_cal_del_target"):
    _de = st.session_state["_cal_del_target"]
    # Algunos gastos fijos antiguos pueden no tener fixed_expense_id guardado
    # (p. ej. creados antes de que ese enlace existiera); sin él no hay cómo
    # ubicar "los futuros", así que en ese caso se cae al flujo simple.
    _es_gasto_fijo = (
        _de["kind"] == "expense" and _de.get("expense_kind") == "fijo" and _de.get("fixed_expense_id")
    )

    @st.dialog("Eliminar")
    def _cal_del_dialog():
        st.warning(
            f"¿Eliminar **{_de['vendor']}** · {_de['label']} · {utils.money(_de['amount'])}? "
            "Esta acción no se puede deshacer."
        )
        if _es_gasto_fijo:
            st.caption(
                "Es un gasto fijo recurrente — ¿eliminas solo este pago, o este y todos "
                "los que vienen después (deja de generarse este gasto de aquí en adelante)?"
            )
            e1, e2, e3 = st.columns(3)
            if e1.button("Solo este", width="stretch"):
                db.delete_expense(_de["ref_id"])
                st.session_state["_cal_del_target"] = None
                st.rerun()
            if e2.button("Este y los futuros", type="primary", width="stretch"):
                db.delete_future_fixed_expenses(_de["fixed_expense_id"], _de["date"])
                st.session_state["_cal_del_target"] = None
                st.rerun()
            if e3.button("Cancelar", width="stretch"):
                st.session_state["_cal_del_target"] = None
                st.rerun()
        else:
            c1, c2 = st.columns(2)
            if c1.button("No, cancelar", width="stretch"):
                st.session_state["_cal_del_target"] = None
                st.rerun()
            if c2.button("Sí, eliminar", type="primary", width="stretch"):
                if _de["kind"] == "invoice":
                    db.delete_invoice(_de["ref_id"])
                elif _de["kind"] == "letra":
                    db.delete_letra(_de["ref_id"])
                else:
                    db.delete_expense(_de["ref_id"])
                st.session_state["_cal_del_target"] = None
                st.rerun()

    _cal_del_dialog()
