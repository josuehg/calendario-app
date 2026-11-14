from datetime import date

import pandas as pd
import streamlit as st
import db
import utils
import ventas

st.title("💵 Ingresos")
st.caption(
    "Ventas/cobros registrados por sucursal, un monto por día (como un cierre "
    "de caja). Junto con la caja que corriges en el Simulador, esto calcula el "
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

ventas.formulario_ventas(branches, incomes, fecha_iso, "inc", "inc_msg")

st.divider()
st.subheader("Ingresos fijos mensuales")
st.caption(
    "Ingresos que llegan una vez al mes, como las comisiones del agente BCP. "
    "Suman al saldo de caja cuando confirmas que llegaron, pero no se mezclan "
    "con la venta de los locales ni con sus indicadores. Mientras no lleguen, "
    "el Calendario y Presupuesto los esperan el último día de su ventana."
)

fixed_incomes = db.list_fixed_incomes()
fixed_receipts = db.list_fixed_income_receipts()
hoy_iso = utils.today_str()
esperados = utils.fixed_income_expected(fixed_incomes, fixed_receipts, hoy_iso)


def _nombre_periodo(periodo):
    return f"{utils.MONTHS_ES[int(periodo[5:7]) - 1]} {periodo[:4]}"


por_confirmar = [e for e in esperados if e["period"] <= hoy_iso[:7]]
for e in por_confirmar:
    with st.container(border=True):
        fc1, fc2 = st.columns([4, 1])
        estado = (
            f"🔴 debía llegar hasta el {utils.fmt_short(e['date'])}" if e["atrasado"]
            else f"suele llegar del {utils.fmt_short(e['date_from'])} al {utils.fmt_short(e['date'])}"
        )
        fc1.markdown(f"**{e['name']}** · {_nombre_periodo(e['period'])} · aprox. {utils.money(e['amount'])}")
        fc1.caption(estado)
        if fc2.button("✅ Llegó", key=f"fi_llego_{e['fixed_income_id']}_{e['period']}", width="stretch"):
            st.session_state["_fi_recibir"] = e
            st.rerun()

proximos = [e for e in esperados if e["period"] > hoy_iso[:7]]
siguiente = {}
for e in proximos:
    siguiente.setdefault(e["fixed_income_id"], e)
if siguiente:
    st.caption("Próximos: " + " · ".join(
        f"{e['name']} {utils.money(e['amount'])} ({utils.fmt_short(e['date_from'])}–{utils.fmt_short(e['date'])})"
        for e in siguiente.values()
    ))
if not fixed_incomes:
    st.info("No hay ingresos fijos configurados. Agrégalos abajo.")

with st.expander("⚙️ Configurar ingresos fijos"):
    for f in fixed_incomes:
        gc1, gc2 = st.columns([4, 1])
        activo = "" if f.get("active", True) else " · ⏸️ desactivado"
        gc1.markdown(
            f"**{f['name']}** · aprox. {utils.money(f['amount'])} · "
            f"del {f['day_from']} al {f['day_to']} de cada mes{activo}"
        )
        if gc2.button("Editar", key=f"fi_edit_{f['id']}", width="stretch"):
            st.session_state["_fi_edit"] = f
            st.rerun()
    with st.form("fi_nuevo", clear_on_submit=True, enter_to_submit=False):
        st.markdown("**Nuevo ingreso fijo**")
        n1, n2 = st.columns([2, 1])
        fi_nombre = n1.text_input("Nombre", placeholder="Ej.: Comisiones BCP")
        fi_monto = n2.number_input("Monto aproximado (S/)", min_value=0.0, step=100.0, format="%.2f")
        d1, d2 = st.columns(2)
        fi_desde = d1.number_input("Suele llegar desde el día", min_value=1, max_value=31, value=1, step=1)
        fi_hasta = d2.number_input("Hasta el día", min_value=1, max_value=31, value=1, step=1)
        if st.form_submit_button("Agregar ingreso fijo", type="primary"):
            if not fi_nombre.strip() or fi_monto <= 0:
                st.warning("Pon un nombre y un monto mayor a 0.")
            elif fi_desde > fi_hasta:
                st.warning("El día 'desde' no puede ser mayor que el día 'hasta'.")
            else:
                db.create_fixed_income({
                    "name": fi_nombre.strip(),
                    "amount": utils.round2(fi_monto),
                    "day_from": int(fi_desde),
                    "day_to": int(fi_hasta),
                    "start_month": hoy_iso[:7],
                })
                st.session_state["inc_msg"] = f"Ingreso fijo agregado: {fi_nombre.strip()}."
                st.rerun()

if fixed_receipts:
    with st.expander(f"📥 Recibidos ({len(fixed_receipts)})"):
        for r in fixed_receipts:
            rc1, rc2 = st.columns([4, 1])
            rc1.write(
                f"**{r['name']}** · {_nombre_periodo(r['period'])} · llegó el "
                f"{utils.fmt_short(r['date'])} · {utils.money(r['amount'])}"
            )
            if rc2.button("Eliminar", key=f"fi_rdel_{r['id']}", width="stretch"):
                db.delete_fixed_income_receipt(r["id"])
                st.session_state["inc_msg"] = (
                    f"Eliminado: {r['name']} de {_nombre_periodo(r['period'])}. Vuelve a quedar por confirmar."
                )
                st.rerun()

# ---------- diálogo: confirmar que llegó ----------
if st.session_state.get("_fi_recibir"):
    _fr = st.session_state["_fi_recibir"]

    def _cerrar_fi_recibir():
        st.session_state["_fi_recibir"] = None

    @st.dialog("Confirmar ingreso recibido", on_dismiss=_cerrar_fi_recibir)
    def _fi_recibir_dialog():
        st.markdown(f"**{_fr['name']}** · {_nombre_periodo(_fr['period'])}")
        fecha = st.date_input("Fecha en que llegó", value=date.today(), key="fi_rec_fecha")
        monto = st.number_input(
            "Monto que llegó (S/)", min_value=0.0, step=0.01, format="%.2f",
            value=float(_fr["amount"]), key="fi_rec_monto",
        )
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", width="stretch"):
            st.session_state["_fi_recibir"] = None
            st.rerun()
        if c2.button("Guardar", type="primary", width="stretch"):
            db.create_fixed_income_receipt({
                "fixed_income_id": _fr["fixed_income_id"],
                "name": _fr["name"],
                "period": _fr["period"],
                "date": fecha.isoformat(),
                "amount": utils.round2(monto),
                "registered_by": utils.current_actor(),
            })
            st.session_state["_fi_recibir"] = None
            st.session_state["inc_msg"] = (
                f"Recibido: {_fr['name']} de {_nombre_periodo(_fr['period'])} · {utils.money(monto)}."
            )
            st.rerun()

    _fi_recibir_dialog()

# ---------- diálogo: editar ingreso fijo ----------
if st.session_state.get("_fi_edit"):
    _fe = st.session_state["_fi_edit"]

    def _cerrar_fi_edit():
        st.session_state["_fi_edit"] = None

    @st.dialog("Editar ingreso fijo", on_dismiss=_cerrar_fi_edit)
    def _fi_edit_dialog():
        nombre = st.text_input("Nombre", value=_fe["name"], key="fi_ed_nombre")
        monto = st.number_input(
            "Monto aproximado (S/)", min_value=0.0, step=100.0, format="%.2f",
            value=float(_fe["amount"]), key="fi_ed_monto",
        )
        d1, d2 = st.columns(2)
        desde = d1.number_input("Desde el día", min_value=1, max_value=31, value=int(_fe["day_from"]), key="fi_ed_desde")
        hasta = d2.number_input("Hasta el día", min_value=1, max_value=31, value=int(_fe["day_to"]), key="fi_ed_hasta")
        activo = st.toggle("Activo (se espera cada mes)", value=_fe.get("active", True), key="fi_ed_activo")
        st.caption("Desactivado deja de esperarse. Eliminar borra la plantilla; lo ya recibido se queda en caja.")
        c1, c2, c3 = st.columns(3)
        if c1.button("🗑️ Eliminar", width="stretch"):
            db.delete_fixed_income(_fe["id"])
            st.session_state["_fi_edit"] = None
            st.rerun()
        if c2.button("Cancelar", width="stretch"):
            st.session_state["_fi_edit"] = None
            st.rerun()
        if c3.button("Guardar", type="primary", width="stretch"):
            if not nombre.strip() or monto <= 0 or desde > hasta:
                st.warning("Revisa: nombre, monto mayor a 0 y 'desde' no mayor que 'hasta'.")
            else:
                db.update_fixed_income(_fe["id"], {
                    "name": nombre.strip(),
                    "amount": utils.round2(monto),
                    "day_from": int(desde),
                    "day_to": int(hasta),
                    "active": activo,
                })
                st.session_state["_fi_edit"] = None
                st.rerun()

    _fi_edit_dialog()

st.divider()
st.subheader("Indicadores")

PERIODOS = ["Últimos 7 días", "Este mes", "Mes pasado", "Últimos 30 días"]
periodo = st.radio("Periodo", PERIODOS, horizontal=True, key="inc_periodo", label_visibility="collapsed")
ind_desde, ind_hasta = utils.income_period(periodo, utils.today_lima())
ind = utils.income_indicators(incomes, branches, ind_desde, ind_hasta)
st.caption(f"Del {utils.fmt_short(ind_desde)} al {utils.fmt_short(ind_hasta)}, comparado con el periodo anterior del mismo largo.")

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Venta total", utils.money(ind["total"]),
    f"{ind['variacion']:+.1f}% vs anterior" if ind["variacion"] is not None else None,
)
k2.metric("Promedio por día", utils.money(ind["promedio_diario"]))
k2.caption(f"{ind['dias_con_registro']} día(s) con registro")
k3.metric("Mejor día", utils.money(ind["mejor_dia"][1]) if ind["mejor_dia"] else "—")
if ind["mejor_dia"]:
    k3.caption(utils.fmt_long(ind["mejor_dia"][0]))
k4.metric("Locales", str(len(branches)))

if ind["total"]:
    st.dataframe(
        pd.DataFrame([
            {
                "Sucursal": f["branch"],
                "Venta": utils.money(f["total"]),
                "Promedio por día abierto": utils.money(f["promedio"]),
                "% del total": f"{f['participacion']:.1f}%",
                "vs anterior": f"{f['variacion']:+.1f}%" if f["variacion"] is not None else "—",
                "Días abiertos": f["dias_abiertos"],
                "Cerrado (0)": f["dias_cerrados"],
                "Sin registrar": f["dias_sin_registrar"],
                "Mejor día": (
                    f"{utils.fmt_short(f['mejor_dia'][0])} · {utils.money(f['mejor_dia'][1])}" if f["mejor_dia"] else "—"
                ),
            }
            for f in ind["por_sucursal"]
        ]),
        hide_index=True, width="stretch",
    )
    faltan = [f["branch"] for f in ind["por_sucursal"] if f["dias_sin_registrar"]]
    if faltan:
        st.caption("Con días sin registrar en este periodo: " + ", ".join(faltan) + ". Los promedios solo cuentan lo registrado.")
else:
    st.info("No hay ingresos registrados en este periodo.")

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
