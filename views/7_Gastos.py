from datetime import date

import streamlit as st
import db
import utils

st.title("💸 Gastos fijos y variables")
st.caption(
    "Gastos que no son facturas de proveedor: alquiler, planilla, servicios, "
    "impuestos, etc. Los **fijos** se definen una vez y el sistema los genera "
    "cada mes; los **variables** se registran cuando ocurren. Todo gasto "
    "pendiente aparece en Calendario y Presupuesto (no en Resumen)."
)

db.ensure_expense_instances()

GENERAL = "General / oficina central"
cats = [c["name"] for c in db.list_expense_categories()]
branch_opts = [GENERAL] + db.get_branches()
FX_KEYS = ["fx_name", "fx_cat", "fx_subcat", "fx_branch", "fx_amount", "fx_freq", "fx_day", "fx_day2",
           "fx_start", "fx_endon", "fx_end", "fx_notes", "fx_active", "_fx_cat_prev"]

if not cats:
    st.warning("No hay categorías de gasto. Créalas en **Configuración → Categorías de gasto**.")
    st.stop()

msg = st.session_state.pop("gx_msg", None)
if msg:
    st.success(msg)


def _open_fx_dialog(data):
    for k in FX_KEYS:
        st.session_state.pop(k, None)
    st.session_state.pop("_gx_manage", None)
    st.session_state["_fx_dialog"] = {"data": data}
    # Pre-sembrado para que el guard de "cambió la categoría" (ver _fx_dialog)
    # no borre la subcategoría ya guardada en el primer render.
    st.session_state["_fx_cat_prev"] = data["category"] if data else None


def _open_manage(expense):
    st.session_state.pop("_fx_dialog", None)
    st.session_state["_gx_manage"] = expense


# ---------- urgencia (misma idea que el 🔴/🟠/⚫ del Calendario, como pastilla) ----------

def _urgency(due_date, status):
    if status == "pagado":
        return "Pagado", "good"
    if status == "omitido":
        return "Omitido", "paused"
    today = date.today().isoformat()
    if due_date < today:
        days = (date.fromisoformat(today) - date.fromisoformat(due_date)).days
        return f"Vencido hace {days} día{'s' if days != 1 else ''}", "critical"
    if due_date == today:
        return "Vence hoy", "critical"
    days = (date.fromisoformat(due_date) - date.fromisoformat(today)).days
    return f"Vence en {days} día{'s' if days != 1 else ''}", ("warn" if days <= 7 else "neutral")


_PILL_COLORS = {
    "critical": ("#a83a3a", "rgba(179,63,63,.14)"),
    "warn": ("#a8720f", "rgba(184,128,46,.16)"),
    "neutral": ("#58676d", "rgba(120,130,135,.14)"),
    "paused": ("#8a8f93", "rgba(138,143,147,.16)"),
    "good": ("#2f7d4f", "rgba(47,125,79,.14)"),
}


def _pill(label, cls):
    fg, bg = _PILL_COLORS.get(cls, _PILL_COLORS["neutral"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;'
        f'font-weight:600;padding:3px 9px;border-radius:999px;background:{bg};color:{fg};'
        f'white-space:nowrap"><span style="width:6px;height:6px;border-radius:50%;'
        f'background:currentColor"></span>{label}</span>'
    )


def _group_key(item, by):
    return item["category"] if by == "Categoría" else (item.get("branch") or GENERAL)


def _meta_line(item, by):
    base = (item.get("branch") or GENERAL) if by == "Categoría" else item["category"]
    sub = item.get("subcategory")
    return f"{base} · {sub}" if sub else base


def _pay_day_label(f):
    if f.get("frequency") == "quincenal" and f.get("pay_day_2"):
        return f"Días {f['pay_day']} y {f['pay_day_2']}"
    return f"Día {f['pay_day']}"


def _monthly_amount(f):
    """El monto es por cuota; para totales 'al mes' hay que multiplicarlo por
    cuántas veces se paga al mes (2 si es quincenal)."""
    return float(f["amount"]) * utils.occurrences_per_month(f)


def _render_fx_row(f, group_by, next_pend_by_fx):
    if f["active"]:
        nxt = next_pend_by_fx.get(f["id"])
        lbl, cls = _urgency(nxt["due_date"], nxt["status"]) if nxt else ("Sin cuota generada", "neutral")
    else:
        lbl, cls = "Pausado", "paused"
    rc1, rc2, rc3, rc4, rc5 = st.columns([2.6, 1, 1.7, 1.1, 0.9])
    rc1.markdown(f"**{f['name']}**")
    rc1.caption(_meta_line(f, group_by))
    rc2.markdown(_pay_day_label(f))
    rc3.markdown(_pill(lbl, cls), unsafe_allow_html=True)
    rc4.markdown(utils.money(f["amount"]))
    if rc5.button("Editar", key=f"fx_edit_{f['id']}", width="stretch"):
        _open_fx_dialog(f)
        st.rerun()


# st.tabs no recuerda cuál estaba activa entre reruns (vuelve siempre a la
# primera) — molesto porque guardar en un diálogo dispara un rerun. Un radio
# con key sí conserva su valor, así que hace de "pestañas" que sobreviven a
# guardar/editar.
SECTIONS = ["➕ Gasto variable", "🔁 Gastos fijos", "📆 Próximos gastos"]
section = st.radio("Sección", SECTIONS, horizontal=True, key="gx_section", label_visibility="collapsed")
st.divider()

# ============================ GASTO VARIABLE ============================
if section == SECTIONS[0]:
    # Categoría y subcategoría van fuera del form: un st.form no vuelve a
    # correr hasta que se envía, así que adentro la subcategoría no podría
    # filtrarse en vivo según la categoría elegida.
    vcat1, vcat2 = st.columns(2)
    gv_cat = vcat1.selectbox("Categoría", cats, key="gv_cat")
    if st.session_state.get("_gv_cat_prev") != gv_cat:
        st.session_state.pop("gv_subcat", None)
        st.session_state["_gv_cat_prev"] = gv_cat
    gv_subcat_opts = ["— Ninguna —"] + [s["name"] for s in db.list_expense_subcategories(gv_cat)]
    gv_subcat = vcat2.selectbox("Subcategoría (opcional)", gv_subcat_opts, key="gv_subcat")

    with st.form("gx_var_form"):
        c1, c2 = st.columns(2)
        gv_name = c1.text_input("Descripción", placeholder="Ej: Reparación de vitrina")
        gv_branch = c2.selectbox("Sucursal", branch_opts)
        c3, c4 = st.columns(2)
        gv_amount = c3.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f")
        gv_due = c4.date_input("Fecha de pago", value=date.today())
        gv_notes = st.text_area("Notas (opcional)", height=68)
        if st.form_submit_button("Registrar gasto variable", type="primary"):
            if not gv_name.strip() or gv_amount <= 0 or not gv_due:
                st.error("Completa descripción, monto y fecha de pago.")
            else:
                db.create_expense({
                    "kind": "variable",
                    "name": gv_name.strip(),
                    "category": gv_cat,
                    "subcategory": None if gv_subcat == "— Ninguna —" else gv_subcat,
                    "branch": None if gv_branch == GENERAL else gv_branch,
                    "amount": utils.round2(gv_amount),
                    "due_date": gv_due.isoformat(),
                    "status": "pendiente",
                    "notes": gv_notes.strip() or None,
                    "registered_by": utils.current_actor(),
                })
                st.session_state["gx_msg"] = f"Gasto variable registrado: {gv_name.strip()} · {utils.money(gv_amount)}."
                st.rerun()

    st.divider()
    st.subheader("Variables pendientes")
    var_pend = [e for e in db.list_expenses() if e["kind"] == "variable" and e["status"] == "pendiente"]

    if not var_pend:
        st.caption("No hay gastos variables pendientes.")
    else:
        total_var = utils.dsum(e["amount"] for e in var_pend)
        today_str = date.today().isoformat()
        overdue_var = [e for e in var_pend if e["due_date"] < today_str]

        v1, v2 = st.columns(2)
        v1.metric("Total variable pendiente", utils.money(total_var), f"{len(var_pend)} pendiente(s)")
        v2.metric("Vencidos", str(len(overdue_var)),
                  utils.money(utils.dsum(e["amount"] for e in overdue_var)) if overdue_var else "S/ 0.00")

        group_by_var = st.radio("Agrupar por", ["Categoría", "Sucursal"], horizontal=True, key="var_group_by")
        groups_var = {}
        for e in var_pend:
            groups_var.setdefault(_group_key(e, group_by_var), []).append(e)

        for gname, items in sorted(groups_var.items(), key=lambda kv: -sum(i["amount"] for i in kv[1])):
            subtotal = utils.dsum(i["amount"] for i in items)
            share = (subtotal / total_var * 100) if total_var else 0
            with st.expander(f"{gname}  ·  {len(items)}", expanded=True):
                st.markdown(f"**{utils.money(subtotal)}**  ·  {share:.0f}% de lo pendiente")
                st.progress(min(share / 100, 1.0))
                for e in sorted(items, key=lambda i: i["due_date"]):
                    lbl, cls = _urgency(e["due_date"], e["status"])
                    rc1, rc2, rc3, rc4 = st.columns([2.6, 1.6, 1.1, 1])
                    rc1.markdown(f"**{e['name']}**")
                    rc1.caption(_meta_line(e, group_by_var))
                    rc2.markdown(_pill(lbl, cls), unsafe_allow_html=True)
                    rc3.markdown(utils.money(e["amount"]))
                    if rc4.button("Gestionar", key=f"var_mng_{e['id']}", width="stretch"):
                        _open_manage(e)
                        st.rerun()

# ============================ GASTOS FIJOS ============================
elif section == SECTIONS[1]:
    fixed_all = db.list_fixed_expenses()
    active_fixed = [f for f in fixed_all if f["active"]]
    total_fijo = utils.dsum(_monthly_amount(f) for f in active_fixed)

    # próxima cuota pendiente generada por cada plantilla (para "vence más
    # próximo" y la pastilla de cada fila).
    next_pend_by_fx = {}
    for e in db.list_expenses():
        fid = e.get("fixed_expense_id")
        if fid and e["status"] == "pendiente":
            cur = next_pend_by_fx.get(fid)
            if not cur or e["due_date"] < cur["due_date"]:
                next_pend_by_fx[fid] = e

    if not fixed_all:
        st.caption("Aún no hay gastos fijos. Usa **➕ Nuevo gasto fijo** para agregar alquiler, planilla, etc.")
    else:
        by_cat = {}
        for f in active_fixed:
            by_cat[f["category"]] = by_cat.get(f["category"], 0.0) + _monthly_amount(f)
        top_cat = max(by_cat.items(), key=lambda kv: kv[1]) if by_cat else None
        soonest = min(next_pend_by_fx.values(), key=lambda e: e["due_date"]) if next_pend_by_fx else None

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total mensual comprometido", utils.money(total_fijo), f"{len(active_fixed)} activo(s)")
        s2.metric("Activos / pausados", f"{len(active_fixed)} / {len(fixed_all) - len(active_fixed)}")
        if soonest:
            lbl, _cls = _urgency(soonest["due_date"], soonest["status"])
            s3.metric("Vence más próximo", lbl, soonest["name"])
        else:
            s3.metric("Vence más próximo", "—")
        if top_cat and total_fijo:
            s4.metric("Categoría con más peso", utils.money(top_cat[1]),
                      f"{top_cat[0]} · {round(top_cat[1] / total_fijo * 100)}%")
        else:
            s4.metric("Categoría con más peso", "—")

    st.divider()
    c1, c2, c3 = st.columns([1.4, 1, 2])
    group_by_fx = c1.radio("Agrupar por", ["Categoría", "Sucursal"], horizontal=True, key="fx_group_by")
    only_active_fx = c2.checkbox("Solo activos", value=True, key="fx_only_active")
    search_fx = c3.text_input("Buscar", key="fx_search", placeholder="🔎 Buscar gasto fijo",
                              label_visibility="collapsed")

    if st.button("➕ Nuevo gasto fijo"):
        _open_fx_dialog(None)
        st.rerun()

    rows_fx = [
        f for f in fixed_all
        if (not only_active_fx or f["active"])
        and (not search_fx.strip() or search_fx.strip().lower() in f["name"].lower())
    ]

    if fixed_all and not rows_fx:
        st.caption("Ningún gasto fijo con esos filtros.")
    elif fixed_all:
        groups_fx = {}
        for f in rows_fx:
            groups_fx.setdefault(_group_key(f, group_by_fx), []).append(f)
        grand = total_fijo or 1

        for gname, items in sorted(groups_fx.items(), key=lambda kv: -sum(_monthly_amount(i) for i in kv[1] if i["active"])):
            g_subtotal = utils.dsum(_monthly_amount(i) for i in items if i["active"])
            share = g_subtotal / grand * 100 if grand else 0
            with st.expander(f"{gname}  ·  {len(items)}", expanded=True):
                st.markdown(f"**{utils.money(g_subtotal)}**  ·  {share:.0f}% del total activo")
                st.progress(min(share / 100, 1.0))

                # Desglose por subcategoría dentro de la categoría — solo si
                # alguien la usa aquí (si no, sería ruido). Streamlit no deja
                # anidar un expander dentro de otro, así que cada subcategoría
                # es un sub-encabezado, no un desplegable propio.
                if group_by_fx == "Categoría" and any(f.get("subcategory") for f in items):
                    subgroups = {}
                    for f in items:
                        subgroups.setdefault(f.get("subcategory"), []).append(f)
                    ordered_subs = sorted(
                        subgroups.items(),
                        key=lambda kv: (kv[0] is None, -sum(_monthly_amount(i) for i in kv[1] if i["active"])),
                    )
                    for idx, (sub_name, sub_items) in enumerate(ordered_subs):
                        if idx > 0:
                            st.divider()
                        sub_subtotal = utils.dsum(_monthly_amount(i) for i in sub_items if i["active"])
                        sub_share = sub_subtotal / grand * 100 if grand else 0
                        st.markdown(
                            f"**↳ {sub_name or 'Sin subcategoría'}**  ·  {len(sub_items)}  ·  "
                            f"{utils.money(sub_subtotal)}  ·  {sub_share:.0f}%"
                        )
                        for f in sorted(sub_items, key=lambda i: (not i["active"], i["name"])):
                            _render_fx_row(f, group_by_fx, next_pend_by_fx)
                else:
                    for f in sorted(items, key=lambda i: (not i["active"], i["name"])):
                        _render_fx_row(f, group_by_fx, next_pend_by_fx)

# ============================ PRÓXIMOS GASTOS ============================
else:
    all_exp = db.list_expenses()
    f1, f2, f3, f4 = st.columns(4)
    f_branch = f1.selectbox("Sucursal", ["Todas"] + branch_opts, key="gx_f_branch")
    f_cat = f2.selectbox("Categoría", ["Todas"] + cats, key="gx_f_cat")
    f_status = f3.selectbox("Estado", ["Pendientes", "Pagados", "Omitidos", "Todos"], key="gx_f_status")
    f_group = f4.selectbox("Agrupar por", ["Categoría", "Sucursal", "Sin agrupar"], key="gx_f_group")

    f5, f6 = st.columns(2)
    f_from = f5.date_input("Vencimiento desde", value=None, key="gx_f_from")
    f_to = f6.date_input("Vencimiento hasta", value=None, key="gx_f_to")
    if f_from and f_to and f_from > f_to:
        st.error("«Vencimiento desde» no puede ser posterior a «Vencimiento hasta».")

    status_map = {"Pendientes": "pendiente", "Pagados": "pagado", "Omitidos": "omitido"}
    rows = []
    for e in all_exp:
        if f_status != "Todos" and e["status"] != status_map[f_status]:
            continue
        eb = e.get("branch") or GENERAL
        if f_branch != "Todas" and eb != f_branch:
            continue
        if f_cat != "Todas" and e["category"] != f_cat:
            continue
        if f_from and e["due_date"] < f_from.isoformat():
            continue
        if f_to and e["due_date"] > f_to.isoformat():
            continue
        rows.append(e)

    if not rows:
        st.caption("No hay gastos con esos filtros.")
    else:
        total = utils.dsum(e["amount"] for e in rows)
        today_str = date.today().isoformat()
        week_end = utils.add_days(today_str, 6)
        overdue = [e for e in rows if e["status"] == "pendiente" and e["due_date"] < today_str]
        this_week = [e for e in rows if e["status"] == "pendiente" and today_str <= e["due_date"] <= week_end]

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total filtrado", utils.money(total), f"{len(rows)} gasto(s)")
        s2.metric("Vencidos", str(len(overdue)),
                  utils.money(utils.dsum(e["amount"] for e in overdue)) if overdue else "S/ 0.00")
        s3.metric("Vence esta semana", str(len(this_week)),
                  utils.money(utils.dsum(e["amount"] for e in this_week)) if this_week else "S/ 0.00")
        s4.metric("Gastos listados", str(len(rows)))

        st.divider()
        if f_group == "Sin agrupar":
            groups = {"Todos": rows}
        else:
            groups = {}
            for e in rows:
                groups.setdefault(_group_key(e, f_group), []).append(e)

        grand = total or 1
        for gname, items in sorted(groups.items(), key=lambda kv: -sum(i["amount"] for i in kv[1])):
            subtotal = utils.dsum(i["amount"] for i in items)
            header = f"{gname}  ·  {len(items)}" if f_group != "Sin agrupar" else f"{len(items)} gasto(s)"
            with st.expander(header, expanded=True):
                if f_group != "Sin agrupar":
                    share = subtotal / grand * 100 if grand else 0
                    st.markdown(f"**{utils.money(subtotal)}**  ·  {share:.0f}%")
                    st.progress(min(share / 100, 1.0))
                for e in sorted(items, key=lambda i: i["due_date"]):
                    lbl, cls = _urgency(e["due_date"], e["status"])
                    rc1, rc2, rc3, rc4, rc5 = st.columns([2.6, 1.5, 1.9, 1.1, 1])
                    rc1.markdown(f"**{e['name']}**")
                    cat_txt = e["category"] + (f" · {e['subcategory']}" if e.get("subcategory") else "")
                    rc1.caption(f"{'Fijo' if e['kind'] == 'fijo' else 'Variable'} · {cat_txt} · {e.get('branch') or GENERAL}")
                    rc2.markdown(_pill(lbl, cls), unsafe_allow_html=True)
                    meta2 = f"registró: {e.get('registered_by') or '—'}"
                    if e["status"] == "pagado" and e.get("paid_by"):
                        meta2 += f" · pagó: {e['paid_by']}"
                    rc3.caption(meta2)
                    rc4.markdown(utils.money(e["amount"]))
                    if e["status"] == "pendiente":
                        if rc5.button("Gestionar", key=f"gx_mng_{e['id']}", width="stretch"):
                            _open_manage(e)
                            st.rerun()

# ==================== UN SOLO DIÁLOGO A LA VEZ ====================
# Streamlit no permite abrir dos diálogos en el mismo run. Los tabs se
# renderizan todos siempre, así que el diálogo se decide aquí, una vez.
_fx = st.session_state.get("_fx_dialog")
_mng = st.session_state.get("_gx_manage")

if _fx:
    ed = _fx.get("data")

    @st.dialog("Editar gasto fijo" if ed else "Nuevo gasto fijo")
    def _fx_dialog():
        name = st.text_input("Nombre", value=ed["name"] if ed else "", key="fx_name",
                             placeholder="Ej: Alquiler local Miraflores")
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Categoría", cats,
                           index=cats.index(ed["category"]) if ed and ed["category"] in cats else 0,
                           key="fx_cat")
        # Si la categoría cambió (respecto al render anterior), la subcategoría
        # ya no es válida para la nueva lista de opciones: se resetea antes de
        # instanciar el selectbox (si no, Streamlit truena con un valor que ya
        # no está entre las opciones).
        if st.session_state.get("_fx_cat_prev") != cat:
            st.session_state.pop("fx_subcat", None)
            st.session_state["_fx_cat_prev"] = cat
        subcat_opts = ["— Ninguna —"] + [s["name"] for s in db.list_expense_subcategories(cat)]
        subcat = c2.selectbox("Subcategoría (opcional)", subcat_opts, key="fx_subcat")

        b_idx = branch_opts.index(ed["branch"]) if ed and ed.get("branch") in branch_opts else 0
        branch = st.selectbox("Sucursal", branch_opts, index=b_idx, key="fx_branch")
        c3, c4 = st.columns(2)
        amount = c3.number_input("Monto por cuota (S/)", min_value=0.0, step=0.01, format="%.2f",
                                 value=float(ed["amount"]) if ed else 0.0, key="fx_amount")
        freq = c4.radio(
            "Frecuencia", ["Mensual", "Quincenal"], horizontal=True, key="fx_freq",
            index=1 if (ed and ed.get("frequency") == "quincenal") else 0,
            help="Quincenal: se paga dos veces al mes, cada una por el monto de arriba (ej. planilla quincenal).",
        )
        if freq == "Quincenal":
            d1, d2 = st.columns(2)
            pay_day = d1.number_input("Día de pago 1 (1–31)", min_value=1, max_value=31, step=1,
                                      value=int(ed["pay_day"]) if ed else 1, key="fx_day")
            pay_day_2 = d2.number_input(
                "Día de pago 2 (1–31)", min_value=1, max_value=31, step=1, key="fx_day2",
                value=int(ed["pay_day_2"]) if (ed and ed.get("pay_day_2")) else 15,
            )
        else:
            pay_day = st.number_input("Día de pago (1–31)", min_value=1, max_value=31, step=1,
                                      value=int(ed["pay_day"]) if ed else 1, key="fx_day")
            pay_day_2 = None
        c5, c6 = st.columns(2)
        start = c5.date_input("Aplica desde",
                              value=date.fromisoformat(ed["start_month"]) if ed and ed.get("start_month") else date.today(),
                              key="fx_start")
        end_on = c6.checkbox(
            "El gasto termina en algún mes", value=bool(ed and ed.get("end_month")), key="fx_endon",
            help="Actívalo solo si el gasto se acaba: un préstamo a 24 cuotas, un alquiler con fin de contrato. "
                 "Para alquileres y planilla que siguen indefinidamente, déjalo apagado. NO es una fecha límite de pago.",
        )
        end = None
        if end_on:
            end = c6.date_input(
                "Mes de la última vez que se paga", key="fx_end",
                value=date.fromisoformat(ed["end_month"]) if ed and ed.get("end_month") else date.today(),
            )
            c6.caption("Solo cuenta el mes; ese mes se incluye.")
        notes = st.text_input("Notas (opcional)", value=(ed.get("notes") or "") if ed else "", key="fx_notes")
        active = st.toggle("Activo (se genera cada mes)", value=ed["active"] if ed else True, key="fx_active")

        st.divider()
        b1, b2 = st.columns(2)
        if b1.button("Guardar", type="primary", width="stretch"):
            if not name.strip() or amount <= 0:
                st.error("Ponle nombre y un monto mayor a 0.")
            elif pay_day_2 and int(pay_day) == int(pay_day_2):
                st.error("Los dos días de pago no pueden ser el mismo.")
            else:
                payload = {
                    "name": name.strip(),
                    "category": cat,
                    "subcategory": None if subcat == "— Ninguna —" else subcat,
                    "branch": None if branch == GENERAL else branch,
                    "amount": utils.round2(amount),
                    "frequency": "quincenal" if freq == "Quincenal" else "mensual",
                    "pay_day": int(pay_day),
                    "pay_day_2": int(pay_day_2) if pay_day_2 else None,
                    "active": bool(active),
                    "start_month": start.replace(day=1).isoformat(),
                    "end_month": end.replace(day=1).isoformat() if end else None,
                    "notes": notes.strip() or None,
                }
                if ed:
                    db.update_fixed_expense(ed["id"], payload)
                else:
                    db.create_fixed_expense(payload)
                st.session_state["_fx_dialog"] = None
                st.session_state["gx_msg"] = f"Gasto fijo guardado: {name.strip()}."
                st.rerun()
        if b2.button("Cancelar", width="stretch"):
            st.session_state["_fx_dialog"] = None
            st.rerun()

        if ed:
            st.divider()
            st.caption(
                "Guardar aplica los cambios (monto, día, etc.) a las **cuotas futuras que "
                "sigan pendientes**; las pagadas y los meses pasados no se tocan. "
                "**Desactivar** quita esas cuotas futuras pendientes. **Eliminar** borra la "
                "plantilla y deja sueltos los gastos ya generados."
            )
            if st.button("🗑️ Eliminar plantilla"):
                db.delete_fixed_expense(ed["id"])
                st.session_state["_fx_dialog"] = None
                st.session_state["gx_msg"] = "Plantilla de gasto fijo eliminada."
                st.rerun()

    _fx_dialog()

elif _mng:
    mng = _mng

    @st.dialog(f"Gasto: {mng['name']}")
    def _manage_dialog():
        cat_line = mng["category"] + (f" · {mng['subcategory']}" if mng.get("subcategory") else "")
        st.write(f"{cat_line} · {mng.get('branch') or 'General'} · vence {utils.fmt_short(mng['due_date'])}")
        new_amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
                                     value=float(mng["amount"]), key="gx_mng_amount")
        if abs(new_amount - float(mng["amount"])) > 0.001:
            if st.button("Guardar nuevo monto"):
                db.update_expense(mng["id"], {"amount": utils.round2(new_amount)})
                st.session_state["_gx_manage"] = None
                st.session_state["gx_msg"] = "Monto actualizado."
                st.rerun()
        st.divider()
        pay_date = st.date_input("Fecha de pago", value=date.today(), key="gx_mng_paydate")
        b1, b2 = st.columns(2)
        if b1.button("✅ Marcar pagado", type="primary", width="stretch"):
            db.set_expense_status(mng["id"], "pagado", pay_date.isoformat(), paid_by=utils.current_actor())
            st.session_state["_gx_manage"] = None
            st.session_state["gx_msg"] = f"Gasto pagado: {mng['name']}."
            st.rerun()
        if mng["kind"] == "fijo":
            if b2.button("⏭️ Omitir este mes", width="stretch"):
                db.set_expense_status(mng["id"], "omitido")
                st.session_state["_gx_manage"] = None
                st.session_state["gx_msg"] = f"Gasto omitido este mes: {mng['name']}."
                st.rerun()
        else:
            if b2.button("🗑️ Eliminar", width="stretch"):
                db.delete_expense(mng["id"])
                st.session_state["_gx_manage"] = None
                st.session_state["gx_msg"] = "Gasto variable eliminado."
                st.rerun()
        if st.button("Cerrar"):
            st.session_state["_gx_manage"] = None
            st.rerun()

    _manage_dialog()
