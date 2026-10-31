import calendar as cal
import html
from datetime import date
import streamlit as st
import db
import utils

st.title("📅 Calendario de pagos")

_CAL_ACTION_KEYS = ["_cal_pay_target", "_cal_edit_target", "_cal_del_target", "_cal_bulk_pay_targets"]


def _cerrar_dialogos_del_dia():
    """Cierra cualquier diálogo de detalle/acción de un día abierto. Necesario
    al cambiar de mes: el botón 'Cerrar' del diálogo limpia _cal_day, pero la
    X nativa de Streamlit para cerrarlo no corre nada de este código — así
    que sin esto, _cal_day queda pegado y el diálogo se reabre solo (mostrando
    el día viejo) en el siguiente rerun, como el de 'Anterior'/'Siguiente'."""
    st.session_state["_cal_day"] = None
    for k in _CAL_ACTION_KEYS:
        st.session_state[k] = None

db.ensure_expense_instances()
invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
expenses = db.list_expenses()
settings = db.get_settings()
track_contado = settings.get("track_contado", True)
events = utils.get_payment_events(
    invoices, letras, canje_facturas, track_contado, expenses,
    letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
    letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
)

TIPOS_CAL = ["Todos", "Facturas a crédito", "Contado", "Letras", "Gastos fijos", "Gastos variables"]
fc1, fc2, fc3 = st.columns([1.2, 1.2, 1])
f_tipo_cal = fc1.selectbox("Tipo", TIPOS_CAL, key="cal_f_tipo")
categorias_cal = ["Todas"] + [c["name"] for c in db.list_expense_categories()]
f_cat_cal = fc2.selectbox("Categoría (solo gastos)", categorias_cal, key="cal_f_categoria")
fc3.write("")
mostrar_pagados = fc3.checkbox("Mostrar pagados", key="cal_f_pagados")


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

# Historial de ya pagados, solo si el toggle está activo — se muestra aparte
# (marca propia en cada día + sección de solo lectura en el diálogo), nunca
# sumado a by_date['amount']/['count'] ni a las métricas del mes, que son
# siempre sobre lo pendiente.
paid_events = utils.get_paid_events(invoices, letras, expenses) if mostrar_pagados else []
paid_events = [e for e in paid_events if _cal_matches(e)]
paid_by_date = {}
for e in paid_events:
    paid_by_date.setdefault(e["date"], []).append(e)

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

# Marca aparte (sin montos) de la "ventana de pago" de cada letra pendiente:
# el día de su vencimiento real y el día límite (vencimiento + plazo máximo
# de gracia). No se suma a info['amount']/['count'] de ningún día — solo es
# una referencia visual de cuándo arranca y hasta cuándo se puede pagar.
_dias_gracia_max = settings.get("letra_dias_gracia_max", 10)
ventana_marcas = {}
for e in events:
    if e["kind"] != "letra":
        continue
    venc = e["vencimiento_real"]
    limite = utils.add_days(venc, _dias_gracia_max)
    detalle = f"{e['vendor']} · {e['label'].split(' (')[0]} · {utils.money(e['amount'])}"
    ventana_marcas.setdefault(venc, []).append(("vence", f"Vence: {detalle}"))
    # Con plazo máximo = típico, el límite cae el mismo día en que la letra
    # ya aparece con su monto: una marca ahí no diría nada nuevo.
    if limite != venc and limite != e["date"]:
        ventana_marcas.setdefault(limite, []).append(("limite", f"Límite de pago: {detalle}"))


def _marcas_html(marcas):
    """Un ícono por letra, cada uno con su propio detalle (proveedor, número,
    monto) al pasar el mouse, más el conteo en texto para que se entienda sin
    leyenda y sin mouse (en celular no hay hover)."""
    vencen = sum(1 for tipo, _ in marcas if tipo == "vence")
    limites = sum(1 for tipo, _ in marcas if tipo == "limite")
    partes = []
    if vencen:
        partes.append("1 letra vence" if vencen == 1 else f"{vencen} letras vencen")
    if limites:
        partes.append("1 límite de pago" if limites == 1 else f"{limites} límites de pago")
    iconos = "".join(
        f"<span style='cursor:help' title='{html.escape(t, quote=True)}'>{'🧾' if tipo == 'vence' else '⏰'}</span>"
        for tipo, t in marcas
    )
    return f"<div style='font-size:10px;color:gray'>{iconos} {' · '.join(partes)}</div>"


c1, c2, c3 = st.columns([1, 2, 1])
if c1.button("← Anterior"):
    m = st.session_state["cal_month"] - 1
    y = st.session_state["cal_year"]
    if m < 1:
        m, y = 12, y - 1
    st.session_state["cal_month"], st.session_state["cal_year"] = m, y
    _cerrar_dialogos_del_dia()
    st.rerun()
if c3.button("Siguiente →"):
    m = st.session_state["cal_month"] + 1
    y = st.session_state["cal_year"]
    if m > 12:
        m, y = 1, y + 1
    st.session_state["cal_month"], st.session_state["cal_year"] = m, y
    _cerrar_dialogos_del_dia()
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

# Todo lo atrasado, no solo del mes que se está viendo (respeta los filtros).
atrasados = sorted((e for e in events if e["overdue"]), key=lambda e: -e["dias_atraso"])
if atrasados:
    with st.expander(f"⚠️ Atrasados: {len(atrasados)} · {utils.money(utils.dsum(e['amount'] for e in atrasados))}"):
        for e in atrasados:
            ac1, ac2, ac3 = st.columns([3, 1.4, 1])
            ac1.markdown(f"**{e['vendor']}**")
            ac1.caption(f"{e['label']} · {e['branch']}")
            ac2.markdown(f"🔴 {utils.fmt_atraso(e['dias_atraso'])}")
            ac3.markdown(f"**{utils.money(e['amount'])}**")

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
                paid_info = paid_by_date.get(ds)
                is_today = ds == today_str
                border = "2px solid #0b5d68" if is_today else "1px solid #d7dee1"
                marcas = ventana_marcas.get(ds)
                marcas_html = _marcas_html(marcas) if marcas else ""
                paid_html = (
                    f"<div style='font-size:10px;color:#2e9e5b'>✅ {len(paid_info)} pagado(s) · "
                    f"{utils.money(utils.dsum(p['amount'] for p in paid_info))}</div>"
                ) if paid_info else ""
                if info:
                    st.markdown(
                        f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                        f"<div style='font-size:12px;color:gray'>{day}</div>"
                        f"<div style='font-family:monospace;font-size:12.5px;font-weight:600;color:{_day_color(ds)}'>{utils.money(info['amount'])}</div>"
                        f"<div style='font-size:11px;color:gray'>{info['count']} pago(s)</div>"
                        f"{marcas_html}{paid_html}"
                        f"</div>", unsafe_allow_html=True)
                    if st.button("👁", key=f"day_{ds}", help="Ver pagos de este día"):
                        st.session_state["_cal_day"] = ds
                        st.rerun()
                elif paid_info:
                    st.markdown(
                        f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                        f"<div style='font-size:12px;color:gray'>{day}</div>{marcas_html}{paid_html}</div>", unsafe_allow_html=True)
                    if st.button("👁", key=f"day_{ds}", help="Ver pagos de este día"):
                        st.session_state["_cal_day"] = ds
                        st.rerun()
                else:
                    st.markdown(
                        f"<div style='border:{border};border-radius:8px;padding:6px;min-height:70px'>"
                        f"<div style='font-size:12px;color:gray'>{day}</div>{marcas_html}</div>", unsafe_allow_html=True)

    st.divider()
    _leyenda = "🔴 Vencido &nbsp;&nbsp; 🟠 Próximos 7 días &nbsp;&nbsp; ⚫ Más adelante"
    if ventana_marcas:
        _leyenda += (
            " &nbsp;&nbsp;&nbsp; 🧾 Letra que vence ese día (pasa el mouse para ver cuál): "
            "su monto se suma días después, no en el total de ese día"
        )
    if paid_by_date:
        _leyenda += " &nbsp;&nbsp;&nbsp; ✅ Ya pagado ese día (tampoco cuenta en el total)"
    st.markdown(_leyenda)

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
        paid_info = paid_by_date.get(ds)
        if not info and not paid_info:
            continue
        hubo_algun_dia = True
        dow_label = DOW_ES[date.fromisoformat(ds).weekday()]
        with st.container(border=True):
            lc1, lc2, lc3, lc4 = st.columns([2.2, 1.3, 1, 1])
            tag = " 🟢" if ds == today_str else ""
            lc1.markdown(f"**{dow_label} {day:02d} de {utils.MONTHS_ES[m-1]}**{tag}")
            if info:
                lc2.markdown(
                    f"<span style='font-family:monospace;font-weight:600;color:{_day_color(ds)}'>{utils.money(info['amount'])}</span>",
                    unsafe_allow_html=True,
                )
                lc3.write(f"{info['count']} pago(s)")
            if lc4.button("Ver", key=f"list_day_{ds}", width="stretch"):
                st.session_state["_cal_day"] = ds
                st.rerun()
            if paid_info:
                st.caption(f"✅ {len(paid_info)} pagado(s) · {utils.money(utils.dsum(p['amount'] for p in paid_info))}")
    if not hubo_algun_dia:
        st.caption("No hay pagos este mes con estos filtros.")
    st.divider()
    _leyenda_lista = "🔴 Vencido &nbsp;&nbsp; 🟠 Próximos 7 días &nbsp;&nbsp; ⚫ Más adelante"
    if paid_by_date:
        _leyenda_lista += " &nbsp;&nbsp;&nbsp; ✅ Ya pagado ese día (no cuenta en el total)"
    st.markdown(_leyenda_lista)

# Un solo diálogo a la vez: mientras se paga/edita/elimina algo, se cierra el del día.
if st.session_state.get("_cal_day") and not any(st.session_state.get(k) for k in _CAL_ACTION_KEYS):
    ds = st.session_state["_cal_day"]
    day_events = by_date.get(ds, {"items": []})["items"]
    day_paid = paid_by_date.get(ds, [])

    @st.dialog(f"Pagos del {utils.fmt_long(ds)}", on_dismiss=_cerrar_dialogos_del_dia)
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
                    if e["kind"] == "letra":
                        _limite = utils.add_days(e["vencimiento_real"], _dias_gracia_max)
                        _aviso_limite = f" · Límite de pago: {utils.fmt_short(_limite)}" if _limite != e["date"] else ""
                        st.caption(f"Vence: {utils.fmt_short(e['vencimiento_real'])}{_aviso_limite}")
                    if e["overdue"]:
                        st.caption(f"🔴 {utils.fmt_atraso(e['dias_atraso'])}")
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

        if day_paid:
            st.divider()
            st.markdown("**✅ Ya pagados ese día**")
            for e in day_paid:
                ref = (
                    f" · Fact. {e['invoice_number']}"
                    if e.get("invoice_number") not in (None, "", "—") and e["kind"] != "expense"
                    else ""
                )
                quien = f" · pagó {e['paid_by']}" if e.get("paid_by") else ""
                st.caption(f"{e['vendor']}{ref} · {e['label']} · {e['branch']} · {utils.money(e['amount'])}{quien}")

        if st.button("Cerrar"):
            st.session_state["_cal_day"] = None
            st.rerun()

    _day_dialog()

# ---------- diálogo: marcar varias como pagadas de una sola vez ----------
if st.session_state.get("_cal_bulk_pay_targets"):
    _targets = st.session_state["_cal_bulk_pay_targets"]

    def _cerrar_bulk_pay():
        st.session_state["_cal_bulk_pay_targets"] = None

    @st.dialog("Marcar varias como pagadas", on_dismiss=_cerrar_bulk_pay)
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

    def _cerrar_cal_pay():
        st.session_state["_cal_pay_target"] = None

    @st.dialog("Marcar como pagado", on_dismiss=_cerrar_cal_pay)
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

    def _cerrar_cal_edit():
        st.session_state["_cal_edit_target"] = None

    @st.dialog("Editar", on_dismiss=_cerrar_cal_edit)
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
        # Para letras, "date" es la fecha esperada de pago (vencimiento +
        # plazo típico), no el vencimiento contractual real — si se editara
        # esa fecha se guardaría por error como el vencimiento. Se edita
        # siempre el vencimiento real (vencimiento_real), que es el que
        # manda en la base de datos.
        fecha_actual = _ee.get("vencimiento_real") if _ee["kind"] == "letra" else _ee["date"]
        label_fecha = "Vencimiento" if _ee["kind"] == "letra" else "Fecha"
        fecha = st.date_input(label_fecha, value=date.fromisoformat(fecha_actual), key="cal_edit_fecha")
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

    def _cerrar_cal_del():
        st.session_state["_cal_del_target"] = None

    @st.dialog("Eliminar", on_dismiss=_cerrar_cal_del)
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
