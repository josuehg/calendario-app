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
FX_KEYS = ["fx_name", "fx_cat", "fx_branch", "fx_amount", "fx_day", "fx_start",
           "fx_endon", "fx_end", "fx_notes", "fx_active"]

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


def _open_manage(expense):
    st.session_state.pop("_fx_dialog", None)
    st.session_state["_gx_manage"] = expense


tab_var, tab_fijo, tab_prox = st.tabs(["➕ Gasto variable", "🔁 Gastos fijos", "📆 Próximos gastos"])

# ============================ GASTO VARIABLE ============================
with tab_var:
    with st.form("gx_var_form"):
        c1, c2 = st.columns(2)
        gv_name = c1.text_input("Descripción", placeholder="Ej: Reparación de vitrina")
        gv_cat = c2.selectbox("Categoría", cats)
        c3, c4, c5 = st.columns(3)
        gv_branch = c3.selectbox("Sucursal", branch_opts)
        gv_amount = c4.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f")
        gv_due = c5.date_input("Fecha de pago", value=date.today())
        gv_notes = st.text_area("Notas (opcional)", height=68)
        if st.form_submit_button("Registrar gasto variable", type="primary"):
            if not gv_name.strip() or gv_amount <= 0 or not gv_due:
                st.error("Completa descripción, monto y fecha de pago.")
            else:
                db.create_expense({
                    "kind": "variable",
                    "name": gv_name.strip(),
                    "category": gv_cat,
                    "branch": None if gv_branch == GENERAL else gv_branch,
                    "amount": utils.round2(gv_amount),
                    "due_date": gv_due.isoformat(),
                    "status": "pendiente",
                    "notes": gv_notes.strip() or None,
                    "registered_by": utils.current_actor(),
                })
                st.session_state["gx_msg"] = f"Gasto variable registrado: {gv_name.strip()} · {utils.money(gv_amount)}."
                st.rerun()

# ============================ GASTOS FIJOS ============================
with tab_fijo:
    if st.button("➕ Nuevo gasto fijo"):
        _open_fx_dialog(None)
        st.rerun()

    fixed = db.list_fixed_expenses()
    if not fixed:
        st.caption("Aún no hay gastos fijos. Usa **➕ Nuevo gasto fijo** para agregar alquiler, planilla, etc.")
    for f in fixed:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1.6, 1.4, 0.9])
            estado = "" if f["active"] else "  · ⏸️ inactivo"
            c1.markdown(f"**{f['name']}**{estado}")
            c1.caption(f"{f['category']} · {f.get('branch') or 'General'}")
            c2.markdown(utils.money(f["amount"]))
            c3.markdown(f"Día {f['pay_day']} de cada mes")
            if c4.button("Editar", key=f"fx_edit_{f['id']}"):
                _open_fx_dialog(f)
                st.rerun()

# ============================ PRÓXIMOS GASTOS ============================
with tab_prox:
    all_exp = db.list_expenses()
    f1, f2, f3 = st.columns(3)
    f_branch = f1.selectbox("Sucursal", ["Todas"] + branch_opts, key="gx_f_branch")
    f_cat = f2.selectbox("Categoría", ["Todas"] + cats, key="gx_f_cat")
    f_status = f3.selectbox("Estado", ["Pendientes", "Pagados", "Omitidos", "Todos"], key="gx_f_status")

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
        rows.append(e)

    if not rows:
        st.caption("No hay gastos con esos filtros.")
    else:
        total = utils.dsum(e["amount"] for e in rows)
        st.markdown(f"**{len(rows)} gasto(s) · {utils.money(total)}**")

    today = date.today().isoformat()
    for e in rows:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1.4, 1.5, 1.3])
            tag = {"pendiente": "", "pagado": "  · ✅ pagado", "omitido": "  · ⏭️ omitido"}[e["status"]]
            c1.markdown(f"**{e['name']}**{tag}")
            meta = f"{'Fijo' if e['kind'] == 'fijo' else 'Variable'} · {e['category']} · {e.get('branch') or 'General'}"
            meta += f" · registró: {e.get('registered_by') or '—'}"
            if e["status"] == "pagado" and e.get("paid_by"):
                meta += f" · pagó: {e['paid_by']}"
            c1.caption(meta)
            c2.markdown(utils.money(e["amount"]))
            venc = utils.fmt_short(e["due_date"])
            c3.markdown(f"🔴 {venc}" if e["status"] == "pendiente" and e["due_date"] < today else f"📅 {venc}")
            if e["status"] == "pendiente":
                if c4.button("Gestionar", key=f"gx_mng_{e['id']}", width="stretch"):
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
        b_idx = branch_opts.index(ed["branch"]) if ed and ed.get("branch") in branch_opts else 0
        branch = c2.selectbox("Sucursal", branch_opts, index=b_idx, key="fx_branch")
        c3, c4 = st.columns(2)
        amount = c3.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
                                 value=float(ed["amount"]) if ed else 0.0, key="fx_amount")
        pay_day = c4.number_input("Día de pago (1–31)", min_value=1, max_value=31, step=1,
                                  value=int(ed["pay_day"]) if ed else 1, key="fx_day")
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
            else:
                payload = {
                    "name": name.strip(),
                    "category": cat,
                    "branch": None if branch == GENERAL else branch,
                    "amount": utils.round2(amount),
                    "pay_day": int(pay_day),
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
                "Al **desactivar** deja de generarse a futuro (los meses ya generados se "
                "mantienen). **Eliminar** borra la plantilla; los gastos ya generados quedan sueltos."
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
        st.write(f"{mng['category']} · {mng.get('branch') or 'General'} · vence {utils.fmt_short(mng['due_date'])}")
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
