from datetime import date

import streamlit as st
import db
import utils

st.title("💰 Deudas")
st.caption(
    "Capital, tasa y saldo pendiente de tus préstamos — vinculado a los que ya "
    "tienes registrados en Gastos Fijos (Préstamos Pers. Jur., Pers. Nat. y "
    "Usu), así no repites el nombre y la cuota se mantiene sincronizada sola."
)


def _es_prestamo(categoria):
    c = (categoria or "").lower()
    return "préstamo" in c or "prestamo" in c


fixed_all = db.list_fixed_expenses()
fixed_by_id = {f["id"]: f for f in fixed_all}
debts = db.list_debts()


def _cuota_actual(d):
    """La cuota mensual, leída en vivo del gasto fijo vinculado si lo hay
    (para que un cambio ahí se refleje solo, sin tener que re-editar la
    deuda) — si no está vinculada, usa lo guardado a mano."""
    linked = fixed_by_id.get(d.get("fixed_expense_id"))
    return float(linked["amount"]) if linked else d.get("monthly_payment")


active_debts = [d for d in debts if d.get("active", True)]
bancario = [d for d in active_debts if d["debt_type"] == "bancario"]
informal = [d for d in active_debts if d["debt_type"] == "informal"]

c1, c2, c3 = st.columns(3)
c1.metric("Saldo total pendiente", utils.money(utils.dsum(d["balance"] for d in active_debts)))
c2.metric("Bancario / formal", utils.money(utils.dsum(d["balance"] for d in bancario)), f"{len(bancario)} deuda(s)")
c3.metric("Informal", utils.money(utils.dsum(d["balance"] for d in informal)), f"{len(informal)} deuda(s)")

st.divider()

top1, top2 = st.columns([3, 1])
search = top1.text_input(
    "Buscar acreedor", label_visibility="collapsed", placeholder="🔎 Buscar acreedor por nombre",
)
if top2.button("➕ Nueva deuda", width="stretch"):
    st.session_state.pop("_confirm_del_debt", None)
    st.session_state["_debt_dialog"] = {"mode": "new", "data": None}
    st.rerun()

filtered = debts
if search.strip():
    s = search.strip().lower()
    filtered = [d for d in filtered if s in d["creditor"].lower()]

if not filtered:
    st.caption("No se encontró ninguna deuda con ese criterio." if search.strip() else "Aún no has registrado deudas. Usa \"➕ Nueva deuda\" para empezar.")
else:
    for d in sorted(filtered, key=lambda d: (not d.get("active", True), -d["balance"])):
        with st.container(border=True):
            cc1, cc2, cc3 = st.columns([3, 1.4, 1])
            with cc1:
                tipo_icon = "🏦" if d["debt_type"] == "bancario" else "🤝"
                estado = "" if d.get("active", True) else "  · ⏸️ inactiva"
                vinculo = "  · 🔗 vinculada a Gastos Fijos" if d.get("fixed_expense_id") else ""
                st.markdown(f"**{tipo_icon} {d['creditor']}**{estado}{vinculo}")
                tasa_txt = f" · {d['rate_pct']}%/{d['rate_period']}" if d.get("rate_pct") else ""
                cuota = _cuota_actual(d)
                cuota_txt = f" · cuota {utils.money(cuota)}" if cuota else ""
                venc_txt = f" · vence {utils.fmt_short(d['end_date'])}" if d.get("end_date") else ""
                st.caption(f"Capital original {utils.money(d['principal'])}{tasa_txt}{cuota_txt}{venc_txt}")
            with cc2:
                st.markdown(f"**{utils.money(d['balance'])}**")
                st.caption("saldo pendiente")
            with cc3:
                if st.button("Editar", key=f"debt_edit_{d['id']}", width="stretch"):
                    st.session_state.pop("_confirm_del_debt", None)
                    st.session_state["_debt_dialog"] = {"mode": "edit", "data": d}
                    st.rerun()

# ---------- dialog: nueva/editar deuda ----------
dialog_state = st.session_state.get("_debt_dialog")
if dialog_state:
    editing = dialog_state.get("data")

    @st.dialog("Editar deuda" if editing else "Nueva deuda")
    def _debt_dialog():
        loan_fixed = [f for f in fixed_all if _es_prestamo(f["category"])]
        # No se ofrecen los que ya están vinculados a OTRA deuda (evita duplicados).
        linked_elsewhere = {
            d.get("fixed_expense_id") for d in debts
            if d.get("fixed_expense_id") and (not editing or d["id"] != editing["id"])
        }
        candidatos = [f for f in loan_fixed if f["id"] not in linked_elsewhere]

        NINGUNO = "— Ninguno (deuda aparte, no vinculada a un gasto fijo) —"
        fx_by_label = {
            f"{f['name']} · {f['category']} · cuota {utils.money(f['amount'])}": f for f in candidatos
        }

        default_idx = 0
        if editing and editing.get("fixed_expense_id"):
            linked = fixed_by_id.get(editing["fixed_expense_id"])
            if linked:
                lbl = f"{linked['name']} · {linked['category']} · cuota {utils.money(linked['amount'])}"
                fx_by_label.setdefault(lbl, linked)

        opciones_fx = [NINGUNO] + list(fx_by_label.keys())
        if editing and editing.get("fixed_expense_id") and fixed_by_id.get(editing["fixed_expense_id"]):
            linked = fixed_by_id[editing["fixed_expense_id"]]
            lbl = f"{linked['name']} · {linked['category']} · cuota {utils.money(linked['amount'])}"
            default_idx = opciones_fx.index(lbl)

        fx_choice = st.selectbox(
            "Vincular a un préstamo de Gastos Fijos (opcional)", opciones_fx, index=default_idx, key="dd_fx_link",
            help=(
                "Si este préstamo ya está registrado como gasto fijo (con su cuota mensual), "
                "vincúlalo aquí: el nombre y la cuota se toman de ahí y quedan sincronizados."
            ),
        )
        linked_fx = fx_by_label.get(fx_choice)

        if linked_fx:
            st.text_input("Acreedor", value=linked_fx["name"], disabled=True, key="dd_creditor_linked")
            creditor_value = linked_fx["name"]
            default_type = "informal" if "usu" in linked_fx["category"].lower() else "bancario"
            st.caption(f"Cuota mensual (sincronizada con Gastos Fijos): **{utils.money(linked_fx['amount'])}**")
        else:
            creditor_value = st.text_input(
                "Acreedor", value=editing["creditor"] if (editing and not editing.get("fixed_expense_id")) else "",
                key="dd_creditor",
            )
            default_type = editing["debt_type"] if editing else "bancario"

        # Un selectbox con key fija no "se mueve" sola si solo cambia el
        # argumento index= en reruns posteriores — hay que empujar el valor
        # a session_state cuando cambia a qué préstamo está vinculado.
        if st.session_state.get("_dd_fx_prev") != fx_choice:
            st.session_state["_dd_fx_prev"] = fx_choice
            st.session_state["dd_type"] = default_type

        debt_type = st.radio(
            "Tipo", ["bancario", "informal"],
            index=(1 if default_type == "informal" else 0),
            format_func=lambda x: "🏦 Bancario / formal" if x == "bancario" else "🤝 Informal",
            horizontal=True, key="dd_type",
        )
        c1, c2 = st.columns(2)
        principal = c1.number_input(
            "Capital original (S/)", min_value=0.0, step=0.01, format="%.2f",
            value=float(editing["principal"]) if editing else 0.0, key="dd_principal",
        )
        balance = c2.number_input(
            "Saldo pendiente (S/)", min_value=0.0, step=0.01, format="%.2f",
            value=float(editing["balance"]) if editing else 0.0, key="dd_balance",
        )
        c3, c4 = st.columns(2)
        rate_pct = c3.number_input(
            "Tasa (%, opcional)", min_value=0.0, step=0.1, format="%.2f",
            value=float(editing["rate_pct"]) if editing and editing.get("rate_pct") else 0.0, key="dd_rate",
        )
        rate_period = c4.selectbox(
            "Periodo de la tasa", ["mensual", "anual"],
            index=(1 if editing and editing.get("rate_period") == "anual" else 0), key="dd_rate_period",
        )
        monthly_payment_manual = 0.0
        if not linked_fx:
            monthly_payment_manual = st.number_input(
                "Cuota mensual (S/, opcional — informativo, no genera recordatorio)",
                min_value=0.0, step=0.01, format="%.2f",
                value=float(editing["monthly_payment"]) if editing and editing.get("monthly_payment") else 0.0,
                key="dd_cuota",
            )
        c5, c6 = st.columns(2)
        start_date = c5.date_input(
            "Fecha de inicio (opcional)",
            value=date.fromisoformat(editing["start_date"]) if editing and editing.get("start_date") else None,
            key="dd_start",
        )
        end_date = c6.date_input(
            "Fecha de término (opcional)",
            value=date.fromisoformat(editing["end_date"]) if editing and editing.get("end_date") else None,
            key="dd_end",
        )
        notes = st.text_input("Notas (opcional)", value=(editing.get("notes") or "") if editing else "", key="dd_notes")
        active = st.toggle("Activa", value=editing.get("active", True) if editing else True, key="dd_active")

        st.divider()
        b1, b2 = st.columns(2)
        if b1.button("Guardar", type="primary", width="stretch"):
            if not creditor_value.strip() or principal <= 0:
                st.error("Pon el nombre del acreedor (o vincula un préstamo) y el capital original.")
            else:
                payload = {
                    "creditor": creditor_value.strip(),
                    "debt_type": debt_type,
                    "fixed_expense_id": linked_fx["id"] if linked_fx else None,
                    "principal": utils.round2(principal),
                    "balance": utils.round2(balance),
                    "rate_pct": rate_pct if rate_pct > 0 else None,
                    "rate_period": rate_period if rate_pct > 0 else None,
                    "monthly_payment": (
                        float(linked_fx["amount"]) if linked_fx
                        else (utils.round2(monthly_payment_manual) if monthly_payment_manual > 0 else None)
                    ),
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "notes": notes.strip() or None,
                    "active": active,
                }
                if editing:
                    db.update_debt(editing["id"], payload)
                else:
                    db.create_debt(payload)
                st.session_state["_debt_dialog"] = None
                st.success("Deuda guardada.")
                st.rerun()
        if b2.button("Cancelar", width="stretch"):
            st.session_state["_debt_dialog"] = None
            st.session_state.pop("_confirm_del_debt", None)
            st.rerun()

        if editing:
            st.divider()
            if not st.session_state.get("_confirm_del_debt"):
                if st.button("🗑️ Eliminar esta deuda"):
                    st.session_state["_confirm_del_debt"] = True
                    st.rerun()
            else:
                st.warning("¿Seguro que quieres eliminar esta deuda? Esta acción no se puede deshacer.")
                dd1, dd2 = st.columns(2)
                if dd1.button("Sí, eliminar", type="primary", width="stretch"):
                    db.delete_debt(editing["id"])
                    st.session_state["_debt_dialog"] = None
                    st.session_state.pop("_confirm_del_debt", None)
                    st.success("Deuda eliminada.")
                    st.rerun()
                if dd2.button("No, cancelar", width="stretch"):
                    st.session_state["_confirm_del_debt"] = False
                    st.rerun()

    _debt_dialog()
