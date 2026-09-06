import uuid
from datetime import date

import streamlit as st
import db
import utils

st.title("🔁 Letras")

invoices = db.list_invoices()
letras = db.list_letras()
pendientes_credito = [i for i in invoices if i["status"] == "pendiente" and i["doc_type"] == "credito"]

BRANCHES = db.get_branches() + ["Oficina central"]

tab_canje, tab_directa = st.tabs(["Canjear facturas a letras", "Registrar letra ya programada"])

# ============ letra ya programada (sin canje) — se renderiza primero ============
with tab_directa:
    st.caption(
        "Para letras que ya negociaste fuera del sistema. Se registran sueltas, con "
        "su proveedor y fecha, y aparecen en Calendario y Presupuesto igual que las demás."
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

    sueltas = [l for l in letras if not l.get("canje_id")]
    if sueltas:
        st.divider()
        st.subheader("Letras programadas registradas")
        today = date.today().isoformat()
        for l in sorted(sueltas, key=lambda x: x["fecha_vencimiento"]):
            cc1, cc2, cc3, cc4 = st.columns([2.6, 1.3, 1.4, 1])
            estado = "  · ✅ pagada" if l["estado"] == "pagada" else ""
            cc1.markdown(f"**{l.get('vendor') or '—'}**{estado}")
            cc1.caption(f"Letra {l.get('numero') or '—'} · {l.get('branch') or '—'}")
            cc2.markdown(utils.money(l["monto"]))
            venc = utils.fmt_short(l["fecha_vencimiento"])
            cc3.markdown(f"🔴 {venc}" if l["estado"] == "pendiente" and l["fecha_vencimiento"] < today else f"📅 {venc}")
            if l["estado"] == "pendiente":
                if cc4.button("Eliminar", key=f"del_letra_{l['id']}", width="stretch"):
                    st.session_state["_del_letra_id"] = l["id"]
                    st.rerun()

    if st.session_state.get("_del_letra_id"):
        _lid = st.session_state["_del_letra_id"]

        @st.dialog("Eliminar letra")
        def _del_letra_dialog():
            st.write("Se eliminará esta letra programada de forma permanente.")
            d1, d2 = st.columns(2)
            if d1.button("Cancelar", width="stretch"):
                st.session_state["_del_letra_id"] = None
                st.rerun()
            if d2.button("Eliminar", type="primary", width="stretch"):
                db.delete_letra(_lid)
                st.session_state["_del_letra_id"] = None
                st.rerun()

        _del_letra_dialog()

# ============ canjear facturas a letras ============
with tab_canje:
    st.caption("Selecciona una o varias facturas a crédito y agrúpalas en una o varias letras — no necesitan coincidir 1 a 1.")

    if "canje_selected_ids" not in st.session_state:
        st.session_state["canje_selected_ids"] = st.session_state.pop("canje_preselect", [])
    if "canje_letra_ids" not in st.session_state:
        st.session_state["canje_letra_ids"] = []

    if not pendientes_credito:
        st.info("No hay facturas a crédito pendientes de canje.")
        st.stop()

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
    total_facturas = utils.dsum(i["amount"] for i in selected_invoices)

    if not selected_invoices:
        st.warning("Selecciona al menos una factura para continuar.")
        st.stop()

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
                {"numero": l["numero"], "monto": utils.round2(l["monto"]), "fecha_vencimiento": l["fecha_vencimiento"].isoformat()}
                for l in letras_data
            ]
            db.create_canje(selected_ids, letras_payload, created_by=utils.current_actor())
            st.session_state["canje_selected_ids"] = []
            st.session_state["canje_letra_ids"] = []
            st.success(f"Canje registrado: {len(selected_ids)} factura(s) → {len(letras_payload)} letra(s).")
            st.balloons()
