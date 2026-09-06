import uuid
from datetime import date

import streamlit as st
import db
import utils

st.title("🔁 Letras")

invoices = db.list_invoices()
letras = db.list_letras()
canje_facturas = db.list_canje_facturas()
pendientes_credito = [i for i in invoices if i["status"] == "pendiente" and i["doc_type"] == "credito"]

BRANCHES = db.get_branches() + ["Oficina central"]

# canje_id -> facturas agrupadas (para mostrar de qué es cada letra)
inv_by_id = {i["id"]: i for i in invoices}
canje_invs = {}
for cf in canje_facturas:
    inv = inv_by_id.get(cf["invoice_id"])
    if inv:
        canje_invs.setdefault(cf["canje_id"], []).append(inv)

tab_canje, tab_directa, tab_todas = st.tabs(
    ["Canjear facturas a letras", "Registrar letra ya programada", "Todas las letras"]
)

# ============ letra ya programada (sin canje) ============
with tab_directa:
    st.caption(
        "Para letras que ya negociaste fuera del sistema. Se registran sueltas, con su "
        "proveedor y fecha, y aparecen en Calendario y Presupuesto igual que las demás."
    )
    with st.form("letra_directa_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ld_vendor = c1.text_input("Proveedor")
        ld_branch = c2.selectbox("Sucursal", BRANCHES)
        c3, c4, c5 = st.columns(3)
        ld_numero = c3.text_input("N° de letra")
        ld_monto = c4.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f")
        ld_venc = c5.date_input("Vencimiento", value=None)
        ld_notes = st.text_input("Notas (opcional)")
        if st.form_submit_button("Registrar letra", type="primary"):
            if not ld_vendor.strip() or ld_monto <= 0 or not ld_venc:
                st.error("Completa proveedor, monto y vencimiento.")
            else:
                db.create_letra({
                    "numero": ld_numero.strip() or None,
                    "monto": utils.round2(ld_monto),
                    "fecha_vencimiento": ld_venc.isoformat(),
                    "vendor": ld_vendor.strip(),
                    "branch": ld_branch,
                    "notes": ld_notes.strip() or None,
                })
                st.success(f"Letra registrada: {ld_vendor.strip()} · {utils.money(ld_monto)} · vence {utils.fmt_short(ld_venc.isoformat())}.")
                st.rerun()

# ============ todas las letras: editar / eliminar ============
with tab_todas:
    if not letras:
        st.caption("Aún no hay letras registradas.")
    else:
        f1, f2 = st.columns(2)
        f_estado = f1.selectbox("Estado", ["Pendientes", "Pagadas", "Todas"], key="lt_f_estado")
        f_origen = f2.selectbox("Origen", ["Todos", "De un canje", "Programadas sueltas"], key="lt_f_origen")

        vis = []
        for l in letras:
            if f_estado == "Pendientes" and l["estado"] != "pendiente":
                continue
            if f_estado == "Pagadas" and l["estado"] != "pagada":
                continue
            de_canje = bool(l.get("canje_id"))
            if f_origen == "De un canje" and not de_canje:
                continue
            if f_origen == "Programadas sueltas" and de_canje:
                continue
            vis.append(l)

        today = date.today().isoformat()
        st.markdown(f"**{len(vis)} letra(s) · {utils.money(utils.dsum(l['monto'] for l in vis))}**")
        for l in sorted(vis, key=lambda x: x["fecha_vencimiento"]):
            grouped = canje_invs.get(l.get("canje_id"), [])
            if grouped:
                who = ", ".join(sorted({i["vendor"] for i in grouped}))
                sub = f"Canje · {len(grouped)} factura(s): " + ", ".join(i["invoice_number"] for i in grouped)
            else:
                who = l.get("vendor") or "—"
                sub = f"Programada · {l.get('branch') or '—'}"
            with st.container(border=True):
                cc1, cc2, cc3, cc4 = st.columns([2.6, 1.2, 1.3, 1])
                estado = "  · ✅ pagada" if l["estado"] == "pagada" else ""
                cc1.markdown(f"**{who}** · Letra {l.get('numero') or '—'}{estado}")
                cc1.caption(sub)
                cc2.markdown(utils.money(l["monto"]))
                venc = utils.fmt_short(l["fecha_vencimiento"])
                cc3.markdown(f"🔴 {venc}" if l["estado"] == "pendiente" and l["fecha_vencimiento"] < today else f"📅 {venc}")
                if cc4.button("Gestionar", key=f"lt_mng_{l['id']}", width="stretch"):
                    st.session_state["_letra_manage"] = l
                    st.rerun()

    mng = st.session_state.get("_letra_manage")
    if mng:
        de_canje = bool(mng.get("canje_id"))

        @st.dialog(f"Letra {mng.get('numero') or ''}")
        def _letra_dialog():
            if de_canje:
                st.caption(
                    "Es parte de un canje. Editar su monto no ajusta las facturas agrupadas; "
                    "borrarla deja esas facturas con menos cobertura en letras."
                )
            numero = st.text_input("N° de letra", value=mng.get("numero") or "", key="lt_numero")
            c1, c2 = st.columns(2)
            monto = c1.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f",
                                    value=float(mng["monto"]), key="lt_monto")
            venc = c2.date_input("Vencimiento", value=date.fromisoformat(mng["fecha_vencimiento"]), key="lt_venc")
            data = {"numero": numero.strip() or None, "monto": utils.round2(monto),
                    "fecha_vencimiento": venc.isoformat()}
            if not de_canje:
                d1, d2 = st.columns(2)
                data["vendor"] = d1.text_input("Proveedor", value=mng.get("vendor") or "", key="lt_vendor").strip() or None
                b_idx = BRANCHES.index(mng["branch"]) if mng.get("branch") in BRANCHES else 0
                data["branch"] = d2.selectbox("Sucursal", BRANCHES, index=b_idx, key="lt_branch")
                data["notes"] = st.text_input("Notas", value=mng.get("notes") or "", key="lt_notes").strip() or None

            pagada = st.toggle("Marcada como pagada", value=mng["estado"] == "pagada", key="lt_pagada")
            if pagada:
                fp_default = date.fromisoformat(mng["fecha_pago"]) if mng.get("fecha_pago") else date.today()
                fp = st.date_input("Fecha de pago", value=fp_default, key="lt_fpago")
                data.update({"estado": "pagada", "fecha_pago": fp.isoformat(),
                             "paid_by": mng.get("paid_by") or utils.current_actor()})
            else:
                data.update({"estado": "pendiente", "fecha_pago": None, "paid_by": None})

            st.divider()
            b1, b2 = st.columns(2)
            if b1.button("Guardar cambios", type="primary", width="stretch"):
                db.update_letra(mng["id"], data)
                st.session_state["_letra_manage"] = None
                st.session_state["_letra_msg"] = "Letra actualizada."
                st.rerun()
            if b2.button("Cerrar", width="stretch"):
                st.session_state["_letra_manage"] = None
                st.rerun()

            st.divider()
            if not st.session_state.get("_letra_confirm_del"):
                if st.button("🗑️ Eliminar esta letra"):
                    st.session_state["_letra_confirm_del"] = True
                    st.rerun()
            else:
                st.warning("¿Eliminar la letra de forma permanente?")
                x1, x2 = st.columns(2)
                if x1.button("Sí, eliminar", type="primary", width="stretch"):
                    db.delete_letra(mng["id"])
                    st.session_state["_letra_manage"] = None
                    st.session_state["_letra_confirm_del"] = False
                    st.session_state["_letra_msg"] = "Letra eliminada."
                    st.rerun()
                if x2.button("No", width="stretch"):
                    st.session_state["_letra_confirm_del"] = False
                    st.rerun()

        _letra_dialog()

    if st.session_state.pop("_letra_msg", None):
        st.toast("Listo.")

# ============ canjear facturas a letras ============
with tab_canje:
    st.caption("Selecciona una o varias facturas a crédito y agrúpalas en una o varias letras — no necesitan coincidir 1 a 1.")

    if "canje_selected_ids" not in st.session_state:
        st.session_state["canje_selected_ids"] = st.session_state.pop("canje_preselect", [])
    if "canje_letra_ids" not in st.session_state:
        st.session_state["canje_letra_ids"] = []

    if not pendientes_credito:
        st.info("No hay facturas a crédito pendientes de canje.")
    else:
        options = {
            f"{r['vendor']} · Fact. {r['invoice_number']} · {r['branch']} · {utils.money(r['amount'])} · vence {utils.fmt_short(r['due_date'])}": r["id"]
            for r in pendientes_credito
        }
        id_to_label = {v: k for k, v in options.items()}
        default_labels = [id_to_label[i] for i in st.session_state["canje_selected_ids"] if i in id_to_label]

        selected_labels = st.multiselect("Facturas a incluir en este canje", list(options.keys()), default=default_labels)
        selected_ids = [options[l] for l in selected_labels]
        st.session_state["canje_selected_ids"] = selected_ids
        selected_invoices = [i for i in pendientes_credito if i["id"] in selected_ids]

        if not selected_invoices:
            st.warning("Selecciona al menos una factura para continuar.")
        else:
            total_facturas = utils.dsum(i["amount"] for i in selected_invoices)
            st.metric("Total de facturas seleccionadas", utils.money(total_facturas))

            st.divider()
            st.subheader("Letras a generar")

            if not st.session_state["canje_letra_ids"]:
                new_id = str(uuid.uuid4())
                st.session_state["canje_letra_ids"] = [new_id]
                st.session_state[f"numero_{new_id}"] = ""
                st.session_state[f"monto_{new_id}"] = total_facturas
                st.session_state[f"fecha_{new_id}"] = None

            letras_data = []
            for idx, lid in enumerate(st.session_state["canje_letra_ids"]):
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.5])
                numero = c1.text_input(f"N° letra {idx + 1}", key=f"numero_{lid}")
                monto = c2.number_input(f"Monto {idx + 1}", min_value=0.0, step=0.01, format="%.2f", key=f"monto_{lid}")
                fecha = c3.date_input(f"Vencimiento {idx + 1}", key=f"fecha_{lid}", value=None)
                if c4.button("✕", key=f"remove_{lid}", help="Quitar esta letra"):
                    st.session_state["canje_letra_ids"].remove(lid)
                    st.rerun()
                letras_data.append({"numero": numero, "monto": monto, "fecha_vencimiento": fecha})

            if st.button("+ Agregar letra"):
                new_id = str(uuid.uuid4())
                st.session_state["canje_letra_ids"].append(new_id)
                st.session_state[f"numero_{new_id}"] = ""
                st.session_state[f"monto_{new_id}"] = 0.0
                st.rerun()

            total_letras = utils.dsum(l["monto"] or 0 for l in letras_data)
            mismatch = abs(total_letras - total_facturas) > 0.009
            color = ":red" if mismatch else ":green"
            st.markdown(f"Total asignado a letras: {color}[**{utils.money(total_letras)}**] de **{utils.money(total_facturas)}**"
                        + (" — no coincide con el total de las facturas seleccionadas." if mismatch else ""))

            st.divider()
            if st.button("Confirmar canje", type="primary"):
                if any(not l["fecha_vencimiento"] or not l["monto"] or l["monto"] <= 0 for l in letras_data):
                    st.error("Cada letra necesita un monto mayor a 0 y una fecha de vencimiento.")
                else:
                    letras_payload = [
                        {"numero": l["numero"], "monto": utils.round2(l["monto"]),
                         "fecha_vencimiento": l["fecha_vencimiento"].isoformat()}
                        for l in letras_data
                    ]
                    db.create_canje(selected_ids, letras_payload, created_by=utils.current_actor())
                    st.session_state["canje_selected_ids"] = []
                    st.session_state["canje_letra_ids"] = []
                    st.success(f"Canje registrado: {len(selected_ids)} factura(s) → {len(letras_payload)} letra(s).")
                    st.balloons()
