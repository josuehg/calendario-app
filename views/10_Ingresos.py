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

incomes = db.list_incomes()

st.subheader("Registrar ingresos")
inc_fecha = st.date_input("Fecha", value=date.today(), key="inc_fecha")
fecha_iso = inc_fecha.isoformat()

# Lo ya registrado ese día sale precargado: cambiar el monto corrige ese
# registro (no agrega otro, que sumaría doble en el saldo de caja).
registros_del_dia = {}
for r in incomes:
    if r["date"] == fecha_iso:
        registros_del_dia.setdefault(r["branch"], []).append(r)

with st.form("inc_form", enter_to_submit=False, border=False):
    st.caption(
        "Deja vacía la sucursal que aún no tengas. Si el local cerró ese día, pon 0. "
        "Lo ya registrado sale cargado: cámbialo para corregirlo."
    )
    montos = {}
    columnas = st.columns(3)
    for i, branch in enumerate(branches):
        col = columnas[i % 3]
        previos = registros_del_dia.get(branch, [])
        if len(previos) > 1:
            # Varios registros el mismo día (p. ej. "sumar" desde el bot): se
            # corrigen uno por uno en el Historial.
            col.markdown(f"**{branch}**")
            total_previo = utils.dsum(float(r["amount"]) for r in previos)
            col.caption(f"✅ {len(previos)} registros: {utils.money(total_previo)} · corrígelos en el Historial")
            continue
        previo = previos[0] if previos else None
        # La key lleva la fecha y el registro: al cambiar de día (o si el
        # registro cambia) el campo se vuelve a cargar con lo guardado.
        montos[branch] = col.number_input(
            f"{branch} ✅" if previo else branch,
            min_value=0.0, step=0.01, format="%.2f",
            value=float(previo["amount"]) if previo else None,
            placeholder="Sin registrar",
            key=f"inc_monto_{fecha_iso}_{branch}_{previo['id'] if previo else 'nuevo'}_{previo['amount'] if previo else ''}",
        )
    inc_notas = st.text_input("Notas (opcional, se guardan en los nuevos)", key="inc_notas")
    guardar = st.form_submit_button("Guardar ingresos", type="primary")

if guardar:
    # None = sin llenar. 0 es válido (local cerrado ese día).
    nuevos, corregidos = {}, {}
    for branch, monto in montos.items():
        if monto is None:
            continue
        previos = registros_del_dia.get(branch, [])
        if not previos:
            nuevos[branch] = monto
        elif utils.round2(monto) != utils.round2(float(previos[0]["amount"])):
            corregidos[branch] = (previos[0]["id"], monto)
    if not nuevos and not corregidos:
        st.warning("No hay montos nuevos ni cambios para guardar.")
    else:
        for branch, monto in nuevos.items():
            db.create_income({
                "branch": branch,
                "date": fecha_iso,
                "amount": utils.round2(monto),
                "notes": inc_notas.strip() or None,
                "registered_by": utils.current_actor(),
                "source": "app",
            })
        for branch, (income_id, monto) in corregidos.items():
            db.update_income(income_id, {"amount": utils.round2(monto)})
        partes = []
        if nuevos:
            partes.append(f"{len(nuevos)} nuevo(s) · {utils.money(utils.dsum(nuevos.values()))}")
        if corregidos:
            partes.append(f"{len(corregidos)} corregido(s)")
        st.session_state["inc_msg"] = f"Guardado: {' · '.join(partes)} · {utils.fmt_short(fecha_iso)}."
        st.rerun()

st.divider()
st.subheader("Historial")

f1, f2, f3, f4 = st.columns([1.3, 1, 1, 2])
f_branch = f1.selectbox("Filtrar por sucursal", ["Todas"] + branches, key="inc_f_branch")
f_from = f2.date_input("Desde", value=None, key="inc_f_from")
f_to = f3.date_input("Hasta", value=None, key="inc_f_to")

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
