from datetime import date

import streamlit as st
import db
import utils

st.title("💵 Ingresos")
st.caption(
    "Ventas/cobros registrados por sucursal, un monto por día (como un cierre "
    "de caja). Junto con el saldo inicial de Configuración, esto calcula el "
    "saldo de caja real y cuánto queda disponible para comprometer en un "
    "pedido nuevo (ver Presupuesto). También se puede registrar desde el bot "
    "de Telegram con /ingreso."
)

branches = db.get_branches()

msg = st.session_state.pop("inc_msg", None)
if msg:
    st.success(msg)

st.subheader("Registrar ingreso")
c1, c2, c3 = st.columns([1.3, 1, 1])
inc_branch = c1.selectbox("Sucursal", branches, key="inc_branch")
inc_fecha = c2.date_input("Fecha", value=date.today(), key="inc_fecha")
inc_monto = c3.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f", key="inc_monto")
inc_notas = st.text_input("Notas (opcional)", key="inc_notas")

if st.button("Registrar", type="primary"):
    # 0 es válido (local cerrado ese día); el widget ya impide negativos.
    db.create_income({
        "branch": inc_branch,
        "date": inc_fecha.isoformat(),
        "amount": utils.round2(inc_monto),
        "notes": inc_notas.strip() or None,
        "registered_by": utils.current_actor(),
        "source": "app",
    })
    st.session_state["inc_msg"] = f"Registrado: {inc_branch} · {utils.money(inc_monto)} · {utils.fmt_short(inc_fecha.isoformat())}."
    st.rerun()

st.divider()
st.subheader("Historial")

f1, f2, f3, f4 = st.columns([1.3, 1, 1, 2])
f_branch = f1.selectbox("Filtrar por sucursal", ["Todas"] + branches, key="inc_f_branch")
f_from = f2.date_input("Desde", value=None, key="inc_f_from")
f_to = f3.date_input("Hasta", value=None, key="inc_f_to")

incomes = db.list_incomes()
rows = incomes
if f_branch != "Todas":
    rows = [r for r in rows if r["branch"] == f_branch]
if f_from:
    rows = [r for r in rows if r["date"] >= f_from.isoformat()]
if f_to:
    rows = [r for r in rows if r["date"] <= f_to.isoformat()]

f4.metric("Total con estos filtros", utils.money(utils.dsum(r["amount"] for r in rows)))

if not rows:
    st.info("No hay ingresos registrados con estos filtros.")
else:
    for r in rows:
        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            origen = " · vía bot" if r.get("source") == "bot" else ""
            cols[0].write(f"**{r['branch']}** · {utils.fmt_short(r['date'])} · {utils.money(r['amount'])}{origen}")
            meta = f"registró: {r.get('registered_by') or '—'}"
            if r.get("notes"):
                meta += f" · {r['notes']}"
            cols[0].caption(meta)
            if cols[1].button("Editar", key=f"inc_edit_{r['id']}", width="stretch"):
                st.session_state["_inc_edit"] = r
                st.rerun()
            if cols[2].button("Eliminar", key=f"inc_del_{r['id']}", width="stretch"):
                st.session_state["_inc_del"] = r["id"]
                st.rerun()

# ---------- diálogo: editar ----------
if st.session_state.get("_inc_edit"):
    _ie = st.session_state["_inc_edit"]

    def _cerrar_inc_edit():
        st.session_state["_inc_edit"] = None

    @st.dialog("Editar ingreso", on_dismiss=_cerrar_inc_edit)
    def _inc_edit_dialog():
        branch = st.selectbox(
            "Sucursal", branches,
            index=branches.index(_ie["branch"]) if _ie["branch"] in branches else 0,
            key="inc_ed_branch",
        )
        fecha = st.date_input("Fecha", value=date.fromisoformat(_ie["date"]), key="inc_ed_fecha")
        monto = st.number_input(
            "Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
            value=float(_ie["amount"]), key="inc_ed_monto",
        )
        notas = st.text_input("Notas", value=_ie.get("notes") or "", key="inc_ed_notas")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", width="stretch"):
            st.session_state["_inc_edit"] = None
            st.rerun()
        if c2.button("Guardar", type="primary", width="stretch"):
            db.update_income(_ie["id"], {
                "branch": branch,
                "date": fecha.isoformat(),
                "amount": utils.round2(monto),
                "notes": notas.strip() or None,
            })
            st.session_state["_inc_edit"] = None
            st.rerun()

    _inc_edit_dialog()

# ---------- diálogo: eliminar ----------
if st.session_state.get("_inc_del"):
    _iid = st.session_state["_inc_del"]

    def _cerrar_inc_del():
        st.session_state["_inc_del"] = None

    @st.dialog("Eliminar ingreso", on_dismiss=_cerrar_inc_del)
    def _inc_del_dialog():
        st.warning("¿Eliminar este ingreso? Esta acción no se puede deshacer.")
        c1, c2 = st.columns(2)
        if c1.button("No, cancelar", width="stretch"):
            st.session_state["_inc_del"] = None
            st.rerun()
        if c2.button("Sí, eliminar", type="primary", width="stretch"):
            db.delete_income(_iid)
            st.session_state["_inc_del"] = None
            st.rerun()

    _inc_del_dialog()
