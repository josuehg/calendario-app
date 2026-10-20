from datetime import date

import streamlit as st
import db
import utils

st.title("💰 Deudas")
st.caption(
    "Capital, tasa y saldo pendiente de tus préstamos y deudas — separado de la "
    "cuota mensual que ya se registra en Gastos Fijos. Aquí ves cuánto debes en "
    "total, no solo cuánto pagas cada mes."
)

debts = db.list_debts()
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
                st.markdown(f"**{tipo_icon} {d['creditor']}**{estado}")
                tasa_txt = f" · {d['rate_pct']}%/{d['rate_period']}" if d.get("rate_pct") else ""
                cuota_txt = f" · cuota {utils.money(d['monthly_payment'])}" if d.get("monthly_payment") else ""
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
        creditor = st.text_input("Acreedor", value=editing["creditor"] if editing else "", key="dd_creditor")
        debt_type = st.radio(
            "Tipo", ["bancario", "informal"],
            index=(1 if editing and editing["debt_type"] == "informal" else 0),
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
        monthly_payment = st.number_input(
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
            if not creditor.strip() or principal <= 0:
                st.error("Pon el nombre del acreedor y el capital original.")
            else:
                payload = {
                    "creditor": creditor.strip(),
                    "debt_type": debt_type,
                    "principal": utils.round2(principal),
                    "balance": utils.round2(balance),
                    "rate_pct": rate_pct if rate_pct > 0 else None,
                    "rate_period": rate_period if rate_pct > 0 else None,
                    "monthly_payment": utils.round2(monthly_payment) if monthly_payment > 0 else None,
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
